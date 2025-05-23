import base64
import datetime
import io
import json
import re
import struct
import textwrap
from typing import List, Union

import isodate
import structlog
import tiktoken
from colorama import Back, Fore, Style, init
from nltk.tokenize import sent_tokenize
from PIL import Image
from thefuzz import fuzz

from talemate.scene_message import SceneMessage
from talemate.util.dialogue import *
from talemate.util.prompt import *
from talemate.util.response import *

log = structlog.get_logger("talemate.util")

# Initialize colorama
init(autoreset=True)

TIKTOKEN_ENCODING = tiktoken.encoding_for_model("gpt-4-turbo")


def fix_unquoted_keys(s):
    unquoted_key_pattern = r"(?<!\\)(?:(?<=\{)|(?<=,))\s*(\w+)\s*:"
    fixed_string = re.sub(
        unquoted_key_pattern, lambda match: f' "{match.group(1)}":', s
    )
    return fixed_string


def parse_messages_from_str(string: str, names: List[str]) -> List[str]:
    """
    Given a big string containing raw chat history, this function attempts to
    parse it out into a list where each item is an individual message.
    """
    sanitized_names = [re.escape(name) for name in names]

    speaker_regex = re.compile(rf"^({'|'.join(sanitized_names)}): ?", re.MULTILINE)

    message_start_indexes = []
    for match in speaker_regex.finditer(string):
        message_start_indexes.append(match.start())

    if len(message_start_indexes) < 2:
        # Single message in the string.
        return [string.strip()]

    prev_start_idx = message_start_indexes[0]
    messages = []

    for start_idx in message_start_indexes[1:]:
        message = string[prev_start_idx:start_idx].strip()
        messages.append(message)
        prev_start_idx = start_idx

    # add the last message
    messages.append(string[prev_start_idx:].strip())

    return messages


def serialize_chat_history(history: List[str]) -> str:
    """Given a structured chat history object, collapses it down to a string."""
    return "\n".join(history)


def wrap_text(text, character_name, color, width=80):
    """
    Wrap the text at the given width, with optional color for the character name.
    :param text: The text to wrap.
    :param width: The maximum width of each line.
    :param character_name: The character's name to color.
    :param color: The color to apply to the character's name.
    :return: The wrapped text as a string.
    """
    # Split text into lines to maintain existing line breaks
    lines = text.split("\n")

    wrapped_lines = []

    for i, line in enumerate(lines):
        wrapper = textwrap.TextWrapper(width=width)
        # Apply the indent only to the lines that are not the first lines after a line break

        if line.startswith(f"{character_name}: "):
            wrapper.subsequent_indent = " " * (len(character_name) + 2)
        else:
            wrapper.initial_indent = " " * (len(character_name) + 2)
            wrapper.subsequent_indent = " " * (len(character_name) + 2)

        # Wrap each line separately maintaining existing line breaks
        wrapped_line = wrapper.fill(line)

        colored_character_name = colored_text(character_name + ": ", color)

        wrapped_line = wrapped_line.replace(
            character_name + ": ", colored_character_name, 1
        )

        wrapped_lines.append(wrapped_line)

    # Join the wrapped lines to form the final output
    final_text = "\n".join(wrapped_lines)

    # Color emotes on the final text
    final_text = color_emotes(final_text)

    return final_text


def cull_history_list(strings, max_length, buffer):
    removed_strings = []
    total_length = sum(len(s) for s in strings)
    excess_length = total_length - max_length

    if excess_length >= buffer:
        while excess_length > 0:
            removed_string = strings.pop(0)
            removed_strings.append(removed_string)
            excess_length -= len(removed_string)

    return "\n".join(removed_strings), total_length


def colored_text(text, color):
    color_map = {
        "red": Fore.RED,
        "green": Fore.GREEN,
        "blue": Fore.BLUE,
        "cyan": Fore.CYAN,
        "magenta": Fore.MAGENTA,
        "yellow": Fore.YELLOW,
        "white": Fore.WHITE,
        "black": Fore.BLACK,
        "light_red": Fore.LIGHTRED_EX,
        "light_green": Fore.LIGHTGREEN_EX,
        "light_blue": Fore.LIGHTBLUE_EX,
        "light_cyan": Fore.LIGHTCYAN_EX,
        "light_magenta": Fore.LIGHTMAGENTA_EX,
        "light_yellow": Fore.LIGHTYELLOW_EX,
        "light_white": Fore.LIGHTWHITE_EX,
        "light_black": Fore.LIGHTBLACK_EX,
        "bg_red": Back.RED,
        "bg_green": Back.GREEN,
        "bg_blue": Back.BLUE,
        "bg_cyan": Back.CYAN,
        "bg_magenta": Back.MAGENTA,
        "bg_yellow": Back.YELLOW,
        "bg_white": Back.WHITE,
        "bg_black": Back.BLACK,
        "bold": Style.BRIGHT,
        "dim": Style.DIM,
        "normal": Style.NORMAL,
    }

    if color.lower() not in color_map:
        return text + Style.RESET_ALL

    return color_map[color.lower()] + text + Style.RESET_ALL


def color_emotes(text: str, color: str = "blue") -> str:
    """
    Finds strings between * and calls colored_text to color them as emotes.
    :param text: The text containing emotes between * characters.
    :return: The text with colored emotes including * characters.
    """
    emote_regex = re.compile(r"(\*[^\*]+\*)")

    def color_match(match):
        return colored_text(match.group(1), color)

    return emote_regex.sub(color_match, text)


def extract_metadata(img_path, img_format):
    return chara_read(img_path)


def read_metadata_from_png_text(image_path: str) -> dict:
    """
    Reads the character metadata from the tEXt chunk of a PNG image.
    """

    # Read the image
    with open(image_path, "rb") as f:
        png_data = f.read()

    # Split the PNG data into chunks
    offset = 8  # Skip the PNG signature
    while offset < len(png_data):
        length = struct.unpack("!I", png_data[offset : offset + 4])[0]
        chunk_type = png_data[offset + 4 : offset + 8]
        chunk_data = png_data[offset + 8 : offset + 8 + length]
        if chunk_type == b"tEXt":
            keyword, text_data = chunk_data.split(b"\x00", 1)
            if keyword == b"chara":
                return json.loads(base64.b64decode(text_data).decode("utf-8"))
        offset += 12 + length

    raise ValueError("No character metadata found.")


def chara_read(img_url, input_format=None):
    if input_format is None:
        if ".webp" in img_url:
            format = "webp"
        else:
            format = "png"
    else:
        format = input_format

    with open(img_url, "rb") as image_file:
        image_data = image_file.read()
        image = Image.open(io.BytesIO(image_data))

    exif_data = image.getexif()
    if format == "webp":
        try:
            if 37510 in exif_data:
                try:
                    description = exif_data[37510].decode("utf-8")
                except AttributeError:
                    description = fix_unquoted_keys(exif_data[37510])

                try:
                    char_data = json.loads(description)
                except:
                    byte_arr = [int(x) for x in description.split(",")[1:]]
                    uint8_array = bytearray(byte_arr)
                    char_data_string = uint8_array.decode("utf-8")
                    return json.loads("{" + char_data_string)
            else:
                log.warn("chara_load", msg="No chara data found in webp image.")
                return False

            return char_data
        except Exception as err:
            raise
            return False

    elif format == "png":
        with Image.open(img_url) as img:
            img_data = img.info

            if "chara" in img_data:
                base64_decoded_data = base64.b64decode(img_data["chara"]).decode(
                    "utf-8"
                )
                return json.loads(base64_decoded_data)
            if "comment" in img_data:
                base64_decoded_data = base64.b64decode(img_data["comment"]).decode(
                    "utf-8"
                )
                return base64_decoded_data
            else:
                log.warn("chara_load", msg="No chara data found in PNG image.")
                log.warn("chara_load", msg="Trying to read from PNG text.")

                try:
                    return read_metadata_from_png_text(img_url)
                except ValueError:
                    return False
                except Exception as exc:
                    log.error(
                        "chara_load",
                        msg="Error reading metadata from PNG text.",
                        exc_info=exc,
                    )
                    return False
    else:
        return None


def count_tokens(source):
    if isinstance(source, list):
        t = 0
        for s in source:
            t += count_tokens(s)
    elif isinstance(source, (str, SceneMessage)):
        # FIXME: there is currently no good way to determine
        # the model loaded in the client, so we are using the
        # TIKTOKEN_ENCODING for now.
        #
        # So counts through this function are at best an approximation

        t = len(TIKTOKEN_ENCODING.encode(str(source)))
    else:
        log.warn("count_tokens", msg="Unknown type: " + str(type(source)))
        t = 0

    return t


def replace_conditional(input_string: str, params) -> str:
    """
    Replaces all occurrences of {conditional:value:compare:true_value:false_value} in the input string
    with the result of calling the conditional function.

    Args:
        input_string (str): The input string containing {conditional:value:compare:true_value:false_value} patterns.
        value: The value to be passed to the conditional function.

    Returns:
        str: The modified input string with the conditional patterns replaced.
    """
    pattern = r"\{conditional:(.*?):(.*?):(.*?):(.*?)\}"

    def replace_match(match):
        value, compare, true_value, false_value = (
            match.group(1),
            match.group(2),
            match.group(3),
            match.group(4),
        )
        value = value.format(**params)
        if value.lower() == compare.lower():
            return true_value
        return false_value

    modified_string = re.sub(pattern, replace_match, input_string)
    return modified_string


def strip_partial_sentences(text: str) -> str:
    """
    Removes any unfinished sentences from the end of the input text.

    This new version works backwards and doesnt destroy string formatting (newlines etc.)

    Args:
        text (str): The input text to be cleaned.

    Returns:
        str: The cleaned text.
    """
    sentence_endings = [".", "!", "?", '"', "*"]

    # loop backwards through `text` until a sentence ending is found

    for i in range(len(text) - 1, -1, -1):
        if text[i] in sentence_endings:
            return remove_trailing_markers(text[: i + 1])

    return text


def strip_partial_sentences_old(text: str) -> str:
    # Sentence ending characters
    sentence_endings = [".", "!", "?", '"', "*"]

    if not text:
        return text

    # Check if the last character is already a sentence ending
    if text[-1] in sentence_endings:
        return text

    # Split the text into words
    words = text.split()

    # Iterate over the words in reverse order until a sentence ending is found
    for i in range(len(words) - 1, -1, -1):
        if words[i][-1] in sentence_endings:
            return " ".join(words[: i + 1])

    # If no sentence ending is found, return the original text
    return text


def clean_paragraph(paragraph: str) -> str:
    """
    Cleans up a paragraph of text by:
    - Splitting the text against ':' and keeping the right-hand side
    - Removing all characters that aren't a-zA-Z from the beginning of the kept text

    Args:
        paragraph (str): The input paragraph to be cleaned.

    Returns:
        str: The cleaned paragraph.
    """

    # Split the paragraph by ':' and keep the right-hand side
    split_paragraph = paragraph.split(":")
    if len(split_paragraph) > 1:
        kept_text = split_paragraph[1]
    else:
        kept_text = split_paragraph[0]

    # Remove all characters that aren't a-zA-Z from the beginning of the kept text
    cleaned_text = re.sub(r"^[^a-zA-Z]*", "", kept_text)

    return cleaned_text


def clean_message(message: str) -> str:
    message = message.strip()
    message = re.sub(r" +", " ", message)
    return message


def clean_dialogue_old(dialogue: str, main_name: str) -> str:
    # re split by \n{not main_name}: with a max count of 1
    pattern = r"\n(?!{}:).*".format(re.escape(main_name))

    # Splitting the text using the updated regex pattern
    dialogue = re.split(pattern, dialogue)[0]
    dialogue = dialogue.replace(f"{main_name}: ", "")
    dialogue = f"{main_name}: {dialogue}"

    return clean_message(strip_partial_sentences(dialogue))


def clean_dialogue(dialogue: str, main_name: str) -> str:

    cleaned = []

    if not dialogue.startswith(main_name):
        dialogue = f"{main_name}: {dialogue}"

    for line in dialogue.split("\n"):

        if not cleaned:
            cleaned.append(line)
            continue

        if line.startswith(f"{main_name}: "):
            cleaned.append(line[len(main_name) + 2 :])
            continue

        # if line is all capitalized
        # this is likely a new speaker in movie script format, and we
        # bail
        if line.strip().isupper():
            break

        if ":" not in line:
            cleaned.append(line)
            continue

    return clean_message(strip_partial_sentences("\n".join(cleaned)))


def clean_id(name: str) -> str:
    """
    Cleans up a id name by removing all characters that aren't a-zA-Z0-9_-

    Spaces are allowed.

    Args:
        name (str): The input id name to be cleaned.

    Returns:
        str: The cleaned id name.
    """
    # Remove all characters that aren't a-zA-Z0-9_-
    cleaned_name = re.sub(r"[^a-zA-Z0-9_\- ]", "", name)

    return cleaned_name


def duration_to_timedelta(duration):
    """Convert an isodate.Duration object or a datetime.timedelta object to a datetime.timedelta object."""
    # Check if the duration is already a timedelta object
    if isinstance(duration, datetime.timedelta):
        return duration

    # If it's an isodate.Duration object with separate year, month, day, hour, minute, second attributes
    days = int(duration.years * 365 + duration.months * 30 + duration.days)
    seconds = int(duration.tdelta.seconds if hasattr(duration, 'tdelta') else 0)
    return datetime.timedelta(days=days, seconds=seconds)


def timedelta_to_duration(delta):
    """Convert a datetime.timedelta object to an isodate.Duration object."""
    total_days = delta.days
    
    # Convert days back to years and months
    years = total_days // 365
    remaining_days = total_days % 365
    months = remaining_days // 30
    days = remaining_days % 30
    
    # Convert remaining seconds
    seconds = delta.seconds
    hours = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60
    
    return isodate.Duration(
        years=years,
        months=months,
        days=days,
        hours=hours,
        minutes=minutes,
        seconds=seconds
    )


def parse_duration_to_isodate_duration(duration_str):
    """Parse ISO 8601 duration string and ensure the result is an isodate.Duration."""
    parsed_duration = isodate.parse_duration(duration_str)
    if isinstance(parsed_duration, datetime.timedelta):
        return timedelta_to_duration(parsed_duration)
    return parsed_duration


def iso8601_diff(duration_str1, duration_str2):
    # Parse the ISO 8601 duration strings ensuring they are isodate.Duration objects
    duration1 = parse_duration_to_isodate_duration(duration_str1)
    duration2 = parse_duration_to_isodate_duration(duration_str2)

    # Convert to timedelta
    timedelta1 = duration_to_timedelta(duration1)
    timedelta2 = duration_to_timedelta(duration2)

    # Calculate the difference
    difference_timedelta = abs(timedelta1 - timedelta2)

    # Convert back to Duration for further processing
    difference = timedelta_to_duration(difference_timedelta)

    return difference


def flatten_duration_components(years: int, months: int, weeks: int, days: int, 
                              hours: int, minutes: int, seconds: int):
    """
    Flatten duration components based on total duration following specific rules.
    Returns adjusted component values based on the total duration.
    """
    
    total_days = years * 365 + months * 30 + weeks * 7 + days
    total_months = total_days // 30
    
    # Less than 1 day - keep original granularity
    if total_days < 1:
        return years, months, weeks, days, hours, minutes, seconds
    
    # Less than 3 days - show only days and hours
    elif total_days < 3:
        if minutes >= 30:  # Round up hours if 30+ minutes
            hours += 1
        return 0, 0, 0, total_days, hours, 0, 0
    
    # Less than a month - show only days
    elif total_days < 30:
        return 0, 0, 0, total_days, 0, 0, 0
    
    # Less than 6 months - show months and days
    elif total_days < 180:
        new_months = total_days // 30
        new_days = total_days % 30
        return 0, new_months, 0, new_days, 0, 0, 0
    
    # Less than 1 year - show only months
    elif total_months < 12:
        new_months = total_months
        if days > 15:  # Round up months if 15+ days remain
            new_months += 1
        return 0, new_months, 0, 0, 0, 0, 0
    
    # Less than 3 years - show years and months
    elif total_months < 36:
        new_years = total_months // 12
        new_months = total_months % 12
        return new_years, new_months, 0, 0, 0, 0, 0
    
    # More than 3 years - show only years
    else:
        new_years = total_months // 12
        if months >= 6:  # Round up years if 6+ months remain
            new_years += 1
        return new_years, 0, 0, 0, 0, 0, 0

def iso8601_duration_to_human(iso_duration, suffix: str = " ago", 
                            zero_time_default: str = "Recently", flatten: bool = True):
    # Parse the ISO8601 duration string into an isodate duration object
    if not isinstance(iso_duration, isodate.Duration):
        duration = isodate.parse_duration(iso_duration)
    else:
        duration = iso_duration

    # Extract years, months, days, and the time part as seconds
    years, months, days, hours, minutes, seconds = 0, 0, 0, 0, 0, 0

    if isinstance(duration, isodate.Duration):
        years = duration.years
        months = duration.months
        days = duration.days
        hours = duration.tdelta.seconds // 3600
        minutes = (duration.tdelta.seconds % 3600) // 60
        seconds = duration.tdelta.seconds % 60
    elif isinstance(duration, datetime.timedelta):
        days = duration.days
        hours = duration.seconds // 3600
        minutes = (duration.seconds % 3600) // 60
        seconds = duration.seconds % 60

    # Convert days to weeks and days if applicable
    weeks, days = divmod(days, 7)

    # If flattening is requested, adjust the components
    if flatten:
        years, months, weeks, days, hours, minutes, seconds = flatten_duration_components(
            years, months, weeks, days, hours, minutes, seconds
        )

    # Build the human-readable components
    components = []
    if years:
        components.append(f"{years} Year{'s' if years > 1 else ''}")
    if months:
        components.append(f"{months} Month{'s' if months > 1 else ''}")
    if weeks:
        components.append(f"{weeks} Week{'s' if weeks > 1 else ''}")
    if days:
        components.append(f"{days} Day{'s' if days > 1 else ''}")
    if hours:
        components.append(f"{hours} Hour{'s' if hours > 1 else ''}")
    if minutes:
        components.append(f"{minutes} Minute{'s' if minutes > 1 else ''}")
    if seconds:
        components.append(f"{seconds} Second{'s' if seconds > 1 else ''}")

    # Construct the human-readable string
    if len(components) > 1:
        last = components.pop()
        human_str = ", ".join(components) + " and " + last
    elif components:
        human_str = components[0]
    else:
        return zero_time_default

    return f"{human_str}{suffix}"


def iso8601_diff_to_human(start, end, flatten: bool = True):
    if not start or not end:
        return ""

    diff = iso8601_diff(start, end)

    return iso8601_duration_to_human(diff, flatten=flatten)


def iso8601_add(date_a: str, date_b: str) -> str:
    """
    Adds two ISO 8601 durations together.
    """
    # Validate input
    if not date_a or not date_b:
        return "PT0S"

    new_ts = isodate.parse_duration(date_a.strip()) + isodate.parse_duration(
        date_b.strip()
    )
    return isodate.duration_isoformat(new_ts)


def iso8601_correct_duration(duration: str) -> str:
    # Split the string into date and time components using 'T' as the delimiter
    parts = duration.split("T")

    # Handle the date component
    date_component = parts[0]
    time_component = ""

    # If there's a time component, process it
    if len(parts) > 1:
        time_component = parts[1]

        # Check if the time component has any date values (Y, M, D) and move them to the date component
        for char in "YD":  # Removed 'M' from this loop
            if char in time_component:
                index = time_component.index(char)
                date_component += time_component[: index + 1]
                time_component = time_component[index + 1 :]

    # If the date component contains any time values (H, M, S), move them to the time component
    for char in "HMS":
        if char in date_component:
            index = date_component.index(char)
            time_component = date_component[index:] + time_component
            date_component = date_component[:index]

    # Combine the corrected date and time components
    corrected_duration = date_component
    if time_component:
        corrected_duration += "T" + time_component

    return corrected_duration


def fix_faulty_json(data: str) -> str:
    # Fix missing commas
    data = re.sub(r"}\s*{", "},{", data)
    data = re.sub(r"]\s*{", "],{", data)
    data = re.sub(r"}\s*\[", "},{", data)
    data = re.sub(r"]\s*\[", "],[", data)

    # Fix trailing commas
    data = re.sub(r",\s*}", "}", data)
    data = re.sub(r",\s*]", "]", data)

    try:
        json.loads(data)
    except json.JSONDecodeError:
        try:
            json.loads(data + "}")
            return data + "}"
        except json.JSONDecodeError:
            try:
                json.loads(data + "]")
                return data + "]"
            except json.JSONDecodeError:
                return data

    return data


def extract_json(s):
    """
    Extracts a JSON string from the beginning of the input string `s`.

    Parameters:
        s (str): The input string containing a JSON string at the beginning.

    Returns:
        str: The extracted JSON string.
        dict: The parsed JSON object.

    Raises:
        ValueError: If a valid JSON string is not found.
    """
    open_brackets = 0
    close_brackets = 0
    bracket_stack = []
    json_string_start = None
    s = s.lstrip()  # Strip white spaces and line breaks from the beginning
    i = 0

    log.debug("extract_json", s=s)

    # Iterate through the string.
    while i < len(s):
        # Count the opening and closing curly brackets.
        if s[i] == "{" or s[i] == "[":
            bracket_stack.append(s[i])
            open_brackets += 1
            if json_string_start is None:
                json_string_start = i
        elif s[i] == "}" or s[i] == "]":
            bracket_stack
            close_brackets += 1
            # Check if the brackets match, indicating a complete JSON string.
            if open_brackets == close_brackets:
                json_string = s[json_string_start : i + 1]
                # Try to parse the JSON string.
                return json_string, json.loads(json_string)
        i += 1

    if json_string_start is None:
        raise ValueError("No JSON string found.")

    json_string = s[json_string_start:]
    while bracket_stack:
        char = bracket_stack.pop()
        if char == "{":
            json_string += "}"
        elif char == "[":
            json_string += "]"

    json_object = json.loads(json_string)
    return json_string, json_object


def similarity_score(
    line: str, lines: list[str], similarity_threshold: int = 95
) -> tuple[bool, int, str]:
    """
    Checks if a line is similar to any of the lines in the list of lines.

    Arguments:
        line (str): The line to check.
        lines (list): The list of lines to check against.
        threshold (int): The similarity threshold to use when comparing lines.

    Returns:
        bool: Whether a similar line was found.
        int: The similarity score of the line. If no similar line was found, the highest similarity score is returned.
        str: The similar line that was found. If no similar line was found, None is returned.
    """

    highest_similarity = 0

    for existing_line in lines:
        similarity = fuzz.ratio(line, existing_line)
        highest_similarity = max(highest_similarity, similarity)
        # print("SIMILARITY", similarity, existing_line[:32]+"...")
        if similarity >= similarity_threshold:
            return True, similarity, existing_line

    return False, highest_similarity, None


def dedupe_sentences(
    line_a: str,
    line_b: str,
    similarity_threshold: int = 95,
    debug: bool = False,
    split_on_comma: bool = True,
) -> str:
    """
    Will split both lines into sentences and then compare each sentence in line_a
    against similar sentences in line_b. If a similar sentence is found, it will be
    removed from line_a.

    The similarity threshold is used to determine if two sentences are similar.

    Arguments:
        line_a (str): The first line.
        line_b (str): The second line.
        similarity_threshold (int): The similarity threshold to use when comparing sentences.
        debug (bool): Whether to log debug messages.
        split_on_comma (bool): Whether to split line_b sentences on commas as well.

    Returns:
        str: the cleaned line_a.
    """

    line_a_sentences = sent_tokenize(line_a)
    line_b_sentences = sent_tokenize(line_b)

    cleaned_line_a_sentences = []

    if split_on_comma:
        # collect all sentences from line_b that contain a comma
        line_b_sentences_with_comma = []
        for line_b_sentence in line_b_sentences:
            if "," in line_b_sentence:
                line_b_sentences_with_comma.append(line_b_sentence)

        # then split all sentences in line_b_sentences_with_comma on the comma
        # and extend line_b_sentences with the split sentences, making sure
        # to strip whitespace from the beginning and end of each sentence

        for line_b_sentence in line_b_sentences_with_comma:
            line_b_sentences.extend([s.strip() for s in line_b_sentence.split(",")])

    for line_a_sentence in line_a_sentences:
        similar_found = False
        for line_b_sentence in line_b_sentences:
            similarity = fuzz.ratio(line_a_sentence, line_b_sentence)
            if similarity >= similarity_threshold:
                if debug:
                    log.debug(
                        "DEDUPE SENTENCE",
                        similarity=similarity,
                        line_a_sentence=line_a_sentence,
                        line_b_sentence=line_b_sentence,
                    )
                similar_found = True
                break
        if not similar_found:
            cleaned_line_a_sentences.append(line_a_sentence)

    return " ".join(cleaned_line_a_sentences)


def dedupe_string_old(
    s: str, min_length: int = 32, similarity_threshold: int = 95, debug: bool = False
) -> str:
    """
    Removes duplicate lines from a string.

    Arguments:
        s (str): The input string.
        min_length (int): The minimum length of a line to be checked for duplicates.
        similarity_threshold (int): The similarity threshold to use when comparing lines.
        debug (bool): Whether to log debug messages.

    Returns:
        str: The deduplicated string.
    """

    lines = s.split("\n")
    deduped = []

    for line in lines:
        stripped_line = line.strip()
        if len(stripped_line) > min_length:
            similar_found = False
            for existing_line in deduped:
                similarity = fuzz.ratio(stripped_line, existing_line.strip())
                if similarity >= similarity_threshold:
                    similar_found = True
                    if debug:
                        log.debug(
                            "DEDUPE",
                            similarity=similarity,
                            line=line,
                            existing_line=existing_line,
                        )
                    break
            if not similar_found:
                deduped.append(line)
        else:
            deduped.append(line)  # Allow shorter strings without dupe check

    return "\n".join(deduped)


def dedupe_string(
    s: str, min_length: int = 32, similarity_threshold: int = 95, debug: bool = False
) -> str:
    """
    Removes duplicate lines from a string going from the bottom up, excluding content within code blocks.
    Code blocks are identified by lines starting with triple backticks.

    Arguments:
        s (str): The input string.
        min_length (int): The minimum length of a line to be checked for duplicates.
        similarity_threshold (int): The similarity threshold to use when comparing lines.
        debug (bool): Whether to log debug messages.

    Returns:
        str: The deduplicated string.
    """
    lines = s.split("\n")
    deduped = []
    current_in_codeblock = False
    existing_in_codeblock = False
    
    for line in reversed(lines):
        stripped_line = line.strip()
        
        # Check for code block markers in current line
        if stripped_line.startswith("```"):
            current_in_codeblock = not current_in_codeblock
            deduped.append(line)
            continue
            
        # Skip deduping for lines in code blocks
        if current_in_codeblock:
            deduped.append(line)
            continue
            
        if len(stripped_line) > min_length:
            similar_found = False
            existing_in_codeblock = False
            
            for existing_line in deduped:
                # Track code block state for existing lines
                if existing_line.strip().startswith("```"):
                    existing_in_codeblock = not existing_in_codeblock
                    continue
                
                # Skip comparing if either line is in a code block    
                if existing_in_codeblock:
                    continue
                    
                similarity = fuzz.ratio(stripped_line, existing_line.strip())
                if similarity >= similarity_threshold:
                    similar_found = True
                    if debug:
                        log.debug(
                            "DEDUPE",
                            similarity=similarity,
                            line=line,
                            existing_line=existing_line,
                        )
                    break
            if not similar_found:
                deduped.append(line)
        else:
            deduped.append(line)

    return "\n".join(reversed(deduped))

def remove_extra_linebreaks(s: str) -> str:
    """
    Removes extra line breaks from a string.

    Parameters:
        s (str): The input string.

    Returns:
        str: The string with extra line breaks removed.
    """
    return re.sub(r"\n{3,}", "\n\n", s)


def replace_exposition_markers(s: str) -> str:
    s = s.replace("(", "*").replace(")", "*")
    s = s.replace("[", "*").replace("]", "*")
    return s


def ensure_dialog_format(line: str, talking_character: str = None, formatting:str = "md") -> str:
    # if "*" not in line and '"' not in line:
    #    if talking_character:
    #        line = line[len(talking_character)+1:].lstrip()
    #        return f"{talking_character}: \"{line}\""
    #    return f"\"{line}\""
    #

    if talking_character:
        line = line[len(talking_character) + 1 :].lstrip()
        
    if line.startswith('*') and line.endswith('*'):
        if line.count("*") == 2 and not line.count('"'):
            return f"{talking_character}: {line}" if talking_character else line

    if line.startswith('"') and line.endswith('"'):
        if line.count('"') == 2 and not line.count('*'):
            return f"{talking_character}: {line}" if talking_character else line

    lines = []

    has_asterisks = "*" in line
    has_quotes = '"' in line

    default_wrap = None
    if has_asterisks and not has_quotes:
        default_wrap = '"'
    elif not has_asterisks and has_quotes:
        default_wrap = "*"

    for _line in line.split("\n"):
        try:
            _line = ensure_dialog_line_format(_line, default_wrap=default_wrap)
        except Exception as exc:
            log.error(
                "ensure_dialog_format",
                msg="Error ensuring dialog line format",
                line=_line,
                exc_info=exc,
            )
            pass

        lines.append(_line)

    if len(lines) > 1:
        line = "\n".join(lines)
    else:
        line = lines[0]

    if talking_character:
        line = f"{talking_character}: {line}"

    if formatting != "md":
        line = line.replace("*", "")

    return line


def ensure_dialog_line_format(line: str, default_wrap: str = None) -> str:
    """
    a Python function that standardizes the formatting of dialogue and action/thought
    descriptions in text strings. This function is intended for use in a text-based
    game where spoken dialogue is encased in double quotes (" ") and actions/thoughts are
    encased in asterisks (* *). The function must correctly format strings, ensuring that
    each spoken sentence and action/thought is properly encased
    """

    i = 0

    segments = []
    segment = None
    segment_open = None
    last_classifier = None

    line = line.strip()

    line = line.replace('"*', '"').replace('*"', '"')

    line = line.replace('*, "', '* "')
    line = line.replace('*. "', '* "')
    line = line.replace("*.", ".*")

    # if the line ends with a whitespace followed by a classifier, strip both from the end
    # as this indicates the remnants of a partial segment that was removed.

    if line.endswith(" *") or line.endswith(' "'):
        line = line[:-2]

    if "*" not in line and '"' not in line and default_wrap and line:
        # if the line is not wrapped in either asterisks or quotes, wrap it in the default
        # wrap, if specified - when it's specialized it means the line was split and we
        # found the other wrap in one of the segments.
        return f"{default_wrap}{line}{default_wrap}"

    for i in range(len(line)):
        c = line[i]

        # print("segment_open", segment_open)
        # print("segment", segment)

        if c in ['"', "*"]:
            if segment_open == c:
                # open segment is the same as the current character
                # closing
                segment_open = None
                segment += c
                segments += [segment.strip()]
                segment = None
                last_classifier = c
            elif segment_open is not None and segment_open != c:
                # open segment is not the same as the current character
                # opening - close the current segment and open a new one

                # if we are at the last character we append the segment
                if i == len(line) - 1 and segment.strip():
                    segment += c
                    segments += [segment.strip()]
                    segment_open = None
                    segment = None
                    last_classifier = c
                    continue

                segments += [segment.strip()]
                segment_open = c
                segment = c
                last_classifier = c
            elif segment_open is None:
                # we're opening a segment
                segment_open = c
                segment = c
                last_classifier = c
        else:
            if segment_open is None and c and c != " ":
                if last_classifier == '"':
                    segment_open = "*"
                    segment = f"{segment_open}{c}"
                elif last_classifier == "*":
                    segment_open = '"'
                    segment = f"{segment_open}{c}"
                else:
                    segment_open = "unclassified"
                    segment = c
            elif segment:
                segment += c

    if segment is not None:
        if segment.strip().strip("*").strip('"'):
            segments += [segment.strip()]

    for i in range(len(segments)):
        segment = segments[i]
        if segment in ['"', "*"]:
            if i > 0:
                prev_segment = segments[i - 1]
                if prev_segment and prev_segment[-1] not in ['"', "*"]:
                    segments[i - 1] = f"{prev_segment}{segment}"
                    segments[i] = ""
                    continue

    for i in range(len(segments)):
        segment = segments[i]

        if not segment:
            continue

        if segment[0] == "*" and segment[-1] != "*":
            segment += "*"
        elif segment[-1] == "*" and segment[0] != "*":
            segment = "*" + segment
        elif segment[0] == '"' and segment[-1] != '"':
            segment += '"'
        elif segment[-1] == '"' and segment[0] != '"':
            segment = '"' + segment
        elif segment[0] in ['"', "*"] and segment[-1] == segment[0]:
            continue

        segments[i] = segment

    for i in range(len(segments)):
        segment = segments[i]
        if not segment or segment[0] in ['"', "*"]:
            continue

        prev_segment = segments[i - 1] if i > 0 else None
        next_segment = segments[i + 1] if i < len(segments) - 1 else None

        if prev_segment and prev_segment[-1] == '"':
            segments[i] = f"*{segment}*"
        elif prev_segment and prev_segment[-1] == "*":
            segments[i] = f'"{segment}"'
        elif next_segment and next_segment[0] == '"':
            segments[i] = f"*{segment}*"
        elif next_segment and next_segment[0] == "*":
            segments[i] = f'"{segment}"'

    for i in range(len(segments)):
        segments[i] = clean_uneven_markers(segments[i], '"')
        segments[i] = clean_uneven_markers(segments[i], "*")

    final = " ".join(segment for segment in segments if segment).strip()
    final = final.replace('","', "").replace('"."', "")
    return final


def clean_uneven_markers(chunk: str, marker: str):
    # if there is an uneven number of quotes, remove the last one if its
    # at the end of the chunk. If its in the middle, add a quote to the endc
    count = chunk.count(marker)

    if count % 2 == 1:
        if chunk.endswith(marker):
            chunk = chunk[:-1]
        elif chunk.startswith(marker):
            chunk = chunk[1:]
        elif count == 1:
            chunk = chunk.replace(marker, "")
        else:
            chunk += marker

    return chunk

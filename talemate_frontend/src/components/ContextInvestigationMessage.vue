<template>
  <v-alert  v-if="show" @mouseover="hovered=true" @mouseleave="hovered=false" @click="toggle()" class="clickable" variant="text" :icon="icon" elevation="7" density="compact" :color="getMessageColor('context_investigation', null)">
    <template v-slot:close>
      <v-btn size="x-small" icon @click="deleteMessage" :disabled="uxLocked">
        <v-icon>mdi-close</v-icon>
      </v-btn>
    </template>
    <v-alert-title v-if="title !== ''" class="muted-title text-caption">{{ title }}</v-alert-title>
    
    <div>
      <v-textarea 
        ref="textarea" 
        v-if="editing" 
        v-model="editing_text"
        color="indigo-lighten-4"
        bg-color="black"
        auto-grow
        :hint="autocompleteInfoMessage(autocompleting) + ', Shift+Enter for newline'"
        :loading="autocompleting"
        :disabled="autocompleting"
        @keydown.enter.prevent="handleEnter" 
        @blur="autocompleting ? null : cancelEdit()"
        @keydown.escape.prevent="cancelEdit()">
      </v-textarea>
      <div v-else @dblclick="startEdit()">
        <span v-for="(part, index) in parts" :key="index" :style="getMessageStyle(styleHandlerFromPart(part))">
          {{ part.text }}
        </span>
      </div>
    </div>

    <v-sheet v-if="hovered" rounded="sm" color="transparent">
      <v-chip size="x-small" color="indigo-lighten-4" v-if="editing">
        <v-icon class="mr-1">mdi-pencil</v-icon>
        Editing - Press `enter` to submit. Click anywhere to cancel.</v-chip>
      <v-chip size="x-small" color="grey-lighten-1" v-else-if="!editing && hovered" variant="text" class="mr-1">
        <v-icon>mdi-pencil</v-icon>
        Double-click to edit.</v-chip>
    </v-sheet>
    <div v-else style="height:24px">

    </div>
  </v-alert>
</template>
  
<script>
import { parseText } from '@/utils/textParser';

export default {
  name: 'ContextInvestigationMessage',
  data() {
    return {
      show: true,
      editing: false,
      editing_text: "",
      autocompleting: false,
      hovered: false,
      minimized: false
    }
  },
  computed: {
    title() {
      switch(this.message.sub_type) {
        case "visual-character":
          return `Observing ${this.message.source_arguments.character}`;
        case "visual-scene":
          return "Observing the moment.";
        case "query":
          return this.message.source_arguments.query;
      }
      return "";
    },
    icon() {
      switch(this.message.sub_type) {
        case "visual-character":
          return "mdi-account-eye";
        case "visual-scene":
          return "mdi-image-frame";
        case "query":
          return "mdi-text-search";
      }
      return "mdi-text-search";
    },
    parts() {
      return parseText(this.message.text);
    }
  },
  props: {
    message: Object,
    uxLocked: Boolean,
    isLastMessage: Boolean,
  },
  inject: ['requestDeleteMessage', 'getWebsocket', 'createPin', 'fixMessageContinuityErrors', 'autocompleteRequest', 'autocompleteInfoMessage', 'getMessageStyle', 'getMessageColor'],
  methods: {
    styleHandlerFromPart(part) {
      if(part.type === '"') {
        return 'character';
      }
      return 'context_investigation';
    },
    toggle() {
      if (!this.editing) {
        this.minimized = !this.minimized;
      }
    },
    deleteMessage() {
      this.requestDeleteMessage(this.message.id);
    },
    handleEnter(event) {
      // if ctrl -> autocomplete
      // else -> submit
      // shift -> newline
      if (event.ctrlKey) {
        this.autocompleteEdit();
      } else if (event.shiftKey) {
        this.editing_text += "\n";
      } else {
        this.submitEdit();
      }
    },
    autocompleteEdit() {
      this.autocompleting = true;
      this.autocompleteRequest(
        {
          partial: this.editing_text,
          context: "context_investigation:continue",
        },
        (completion) => {
          this.editing_text += completion;
          this.autocompleting = false;
        },
        this.$refs.textarea
      )
    },
    cancelEdit() {
      this.editing = false;
    },
    startEdit() {
      if (this.uxLocked) return;
      
      this.editing_text = this.message.text;
      this.editing = true;
      this.$nextTick(() => {
        this.$refs.textarea.focus();
      });
    },
    submitEdit() {
      this.getWebsocket().send(JSON.stringify({ 
        type: 'edit_message', 
        id: this.message.id, 
        text: this.editing_text 
      }));
      this.editing = false;
    }
  }
}
</script>
  
<style scoped>
.muted-title {
  opacity: 0.75;
}
</style>
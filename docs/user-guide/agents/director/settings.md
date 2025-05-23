# Settings

## General

![Director agent settings](/talemate/img/0.29.0/director-general-settings.png)

##### Direct

If enabled the director will attempt to direct the scene.

This is currently only relevant if the scene loaded comes with a script file. For the scenes that are currently included that is only true for the **Simulation Suite**.

###### Turns

How many turns to wait before the director makes a decision.

##### Direct Scene

If enabled the director will attempt to direct the scene through narration.

##### Direct Actors

Enables the director to direct the actors in the scene.

Right now this is only triggered manually by the player when the players uses the `Direct actor` toolset from the [Scenario tools](/talemate/user-guide/scenario-tools).

###### Actor Direction Mode

When an actor is given a direction, how is it to be injected into the context

- `Direction`
- `Inner Monologue`

If `Direction` is selected, the actor will be given the direction as a direct instruction, by the director.

If `Inner Monologue` is selected, the actor will be given the direction as a thought.

## Long Term Memory

--8<-- "docs/snippets/tips.md:agent_long_term_memory_settings"

## Dynamic Actions

Dynamic actions are introduced in `0.28.0` and allow the director to generate a set of clickable choices for the player to choose from.

![Director agent dynamic actions settings](/talemate/img/0.29.0/director-dynamic-actions-settings.png)

##### Enable Dynamic Actions

If enabled the director will generate a set of clickable choices for the player to choose from.

##### Chance

The chance that the director will generate a set of dynamic actions when its the players turn.

This ranges from `0` to `1`. `0` means the director will never generate dynamic actions, `1` means the director will always generate dynamic actions.

##### Number of Actions

The number of actions to generate.

##### Never auto progress on action selection

If this is checked and you pick an action, the scene will NOT automatically pass the turn to the next actor.

##### Instructions

Allows you to provide extra specific instructions to director on how to generate the dynamic actions.

For example you could provide a list of actions to choose from, or a list of actions to avoid. Or specify that you always want a certain action to be included.

## Guide Scene

![Director agent guide scene settings](/talemate/img/0.29.0/director-guide-scene-settings.png)

The director can use the summarizer agent's scene analysis to guide characters and the narrator for the next generation, hopefully improving the quality of the generated content.

!!! danger "This may break dumber models"
    The guidance generated is inserted **after** the message history and **right before** the next generation. Some older models may struggle with this and generate incoherent responses.

##### Guide Actors

If enabled the director will guide the actors in the scene.

##### Guide Narrator

If enabled the director will guide the narrator in the scene.

##### Max. Guidance Length

The maximum number of tokens for the guidance. (e.g., how long should the guidance be).
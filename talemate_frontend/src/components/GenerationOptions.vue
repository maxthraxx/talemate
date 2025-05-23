<template>
    <v-sheet class="text-left ma-1">
        
        <span class="text-caption mr-2 text-muted"><v-icon>mdi-auto-fix</v-icon> Generation Settings</span>
        <v-menu>
            <template v-slot:activator="{ props }">
                <v-chip size="small"  v-bind="props" label class="mr-2" :color="(generationOptions.writing_style ? 'highlight5' : 'muted')">
                    <template v-slot:prepend>
                        <v-icon class="mr-1">mdi-script-text</v-icon>
                    </template>
                    <template v-slot:append>
                        <v-icon class="ml-1" v-if="generationOptions.writing_style !== null" @click.stop="generationOptions.writing_style = null">mdi-close-circle-outline</v-icon>
                    </template>
                    {{ generationOptions.writing_style ? generationOptions.writing_style.name : "Writing Style"}}
                </v-chip>
            </template>

            <v-list slim density="compact">
                <v-list-subheader>Writing Styles</v-list-subheader>
                <p class="text-caption text-muted mb-2 ml-4 mr-4">Writing styles can be added in <v-chip size="small" variant="text" class="text-primary" @click="showManagerEditor('templates')" prepend-icon="mdi-cube-scan">templates</v-chip></p>
                <v-list-item v-for="(template, index) in styleTemplates" :key="index" @click="generationOptions.writing_style = template" :prepend-icon="template.favorite ? 'mdi-star' : 'mdi-script-text'">
                    <v-list-item-title>{{ template.name }}</v-list-item-title>
                    <v-list-item-subtitle>{{ template.description }}</v-list-item-subtitle>
                </v-list-item>
            </v-list>
        </v-menu>

        <v-menu>
            <template v-slot:activator="{ props }">
                <v-chip size="small" v-bind="props" label class="mr-2" :color="(generationOptions.spices ? 'highlight4': 'muted')">
                    <template v-slot:prepend>
                        <v-icon class="mr-1" v-if="generationOptions.spice_level == 0.0">mdi-chili-off</v-icon>
                        <v-icon class="mr-1" v-else-if="generationOptions.spice_level >= 0.6">mdi-chili-hot</v-icon>
                        <v-icon class="mr-1" v-else-if="generationOptions.spice_level >= 0.2">mdi-chili-medium</v-icon>
                        <v-icon class="mr-1" v-else-if="generationOptions.spice_level >= 0.0">mdi-chili-mild</v-icon>
                    </template>
                    <template v-slot:append>
                        <v-icon class="ml-3" v-if="generationOptions.spices !== null" @click.stop="generationOptions.spices = null">mdi-close-circle-outline</v-icon>
                    </template>
                    {{ generationOptions.spices ? generationOptions.spices.name : "Spice"}}
                    <span v-if="generationOptions.spices" class="ml-1 mr-3">{{ spiceLevelFormat(generationOptions.spice_level) }}</span>
                    <v-tooltip text="ctrl+click to reduce spice chance to minimum" v-if="generationOptions.spices" location="top">
                        <template v-slot:activator="{ props }">
                            <v-icon v-bind="props" @click.ctrl.stop="generationOptions.spice_level = 0.1" @click.stop="decreaseSpiceLevel">mdi-minus</v-icon>
                        </template>
                    </v-tooltip>
                    <v-tooltip text="ctrl+click to increase spice chance to maximum" v-if="generationOptions.spices" location="top">
                        <template v-slot:activator="{ props }">
                            <v-icon v-bind="props" @click.ctrl.stop="generationOptions.spice_level = 1" @click.stop="increaseSpiceLevel">mdi-plus</v-icon>
                        </template>
                    </v-tooltip>
                </v-chip>
            </template>
            <v-list slim density="compact">
                <v-list-subheader>Select spice</v-list-subheader>
                <p class="text-caption text-muted mb-2 ml-4 mr-4">Spice collections can be added in <v-chip size="small" variant="text" class="text-primary" @click="showManagerEditor('templates')" prepend-icon="mdi-cube-scan">templates</v-chip></p>
                <v-list-item v-for="(template, index) in spiceTemplates" :key="index" @click="generationOptions.spices = template" :prepend-icon="template.favorite ? 'mdi-star' : 'mdi-chili-mild'" @click.ctrl="generationOptions.spice_level = 1">
                    <v-list-item-title>{{ template.name }}</v-list-item-title>
                    <v-list-item-subtitle>{{ template.description }}</v-list-item-subtitle>
                </v-list-item>
            </v-list>
        </v-menu>
    </v-sheet>
</template>
<script>

export default {
    name: "GenerationOptions",
    props: {
        templates: Object,
    },
    data() {
        return {
            generationOptions: {
                writing_style: null,
                spices: null,
                spice_level: 0.1,
            },
        }
    },
    emits: ["change"],
    inject: ["getWebsocket", "registerMessageHandler", "unregisterMessageHandler", "showManagerEditor"],
    watch:{
        generationOptions: {
            deep: true,
            handler() {
                this.$emit("change", this.generationOptions);
            }
        },
        templates: {
            immediate: true,
            handler(templates) {
                // if spices or writing style is set, update it to the new template
                if(this.generationOptions.spices) {
                    let current = this.generationOptions.spices;
                    this.generationOptions.spices = templates.by_type.spices[
                        `${current.group}__${current.uid}`
                    ];
                }
                if(this.generationOptions.writing_style) {
                    let current = this.generationOptions.writing_style;
                    this.generationOptions.writing_style = templates.by_type.writing_style[
                        `${current.group}__${current.uid}`
                    ];
                }
            }
        }
    },
    computed: {
        spiceTemplates() {

            if(!this.templates || !this.templates.by_type.spices)
                return [];

            // return all templates where template_type == 'spices'
            const templates = Object.values(this.templates.by_type.spices)
            // order by `favorite`, `name` (double sort)
            return templates.sort((a, b) => a.favorite == b.favorite ? a.name.localeCompare(b.name) : b.favorite - a.favorite);
        },
        styleTemplates() {

            if(!this.templates || !this.templates.by_type.writing_style)
                return [];

            // return all templates where template_type == 'writing_style'
            const templates =  Object.values(this.templates.by_type.writing_style)
            // order by `favorite`, `name` (double sort)
            return templates.sort((a, b) => a.favorite == b.favorite ? a.name.localeCompare(b.name) : b.favorite - a.favorite);
        }
    },
    methods: {
        loadWritingStyle(template_uid) {
            this.generationOptions.writing_style = this.templates.by_type.writing_style[template_uid] || null;
        },
        openTemplates() {
            this.showManagerEditor("templates");
        },
        spiceLevelFormat(value) {
            // render as %
            return Math.round(value * 100) + "%";
        },
        increaseSpiceLevel() {
            this.generationOptions.spice_level += 0.1;
            if(this.generationOptions.spice_level > 1)
                this.generationOptions.spice_level = 1;
            // to two decimal places
            this.generationOptions.spice_level = Math.round(this.generationOptions.spice_level * 100) / 100;
        },

        decreaseSpiceLevel() {
            this.generationOptions.spice_level -= 0.1;
            if(this.generationOptions.spice_level <= 0)
                this.generationOptions.spice_level = 0.1;
            // to two decimal places
            this.generationOptions.spice_level = Math.round(this.generationOptions.spice_level * 100) / 100;
        },
    }
}

</script>
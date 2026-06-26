<script setup>
// Mounts a Svelte 5 component as an island inside a VitePress (Vue) page. The
// markdown route statically imports its explainer and hands the component (plus
// props) here; we mount it synchronously in onMounted -- before the parent route
// component's onVnodeMounted fires VitePress' content-updated callbacks -- so the
// explainer's <h2> section headings are already in the DOM when the "on this page"
// outline scans for them. The mount target carries `.qtut`, which scopes the dark
// explainer theme to this pane only (see ../../_tut/theme.css).
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { mount, unmount } from 'svelte'

const props = defineProps({
  component: { type: [Object, Function], required: true },
  props: { type: Object, default: () => ({}) },
})

const host = ref(null)
let app = null

onMounted(() => {
  app = mount(props.component, { target: host.value, props: props.props })
})

onBeforeUnmount(() => {
  if (app) {
    unmount(app)
    app = null
  }
})
</script>

<template>
  <div ref="host" class="qtut"></div>
</template>

<script setup>
defineProps({ name: String, size: { type: [Number, String], default: 20 } })
const paths = {
  plus: ['M12 5v14M5 12h14'],
  panel: ['M3 4h18v16H3V4Z','M9 4v16'],
  send: ['M12 20V4M5 11l7-7 7 7'],
  down: ['M12 4v16M5 13l7 7 7-7'],
  copy: ['M9 9h12v12H9V9Z','M5 15H3V3h12v2'],
  home: ['M3 10.5 12 3l9 7.5', 'M5 9v11h5v-6h4v6h5V9'],
  spark: ['m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6L12 3Z'],
  book: ['M12 6c-3-2-6-2-9-1v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1Z', 'M12 6v14'],
  folder: ['M3 7V5h6l2 2h10v13H3V7Z', 'M7 12h10M7 16h6'],
  chat: ['M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-1 1v-9.5a9 9 0 0 1 18 0Z', 'M7 10h10M7 14h6'],
  chart: ['M4 20h17M6 16v-5M12 16V4M18 16V8'],
  settings: ['M4 7h16M4 17h16', 'M8 4v6M16 14v6'],
  calendar: ['M5 5h14v16H5V5Z', 'M8 3v4M16 3v4M5 10h14M9 14h1M14 14h1'],
  news: ['M5 3h14v18H5V3Z', 'M9 7h6M9 11h6M9 15h3'],
  user: ['M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z', 'M4 21v-2a8 8 0 0 1 16 0v2'],
  arrow: ['M5 12h14M13 6l6 6-6 6'],
  search: ['M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z', 'm15 15 6 6'],
  logout: ['M9 4H4v16h5M10 12h11M17 8l4 4-4 4'],
  chevron: ['m9 5 7 7-7 7'],
  heart: ['M20.8 4.8a5.5 5.5 0 0 0-7.8 0L12 5.9l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.4a5.5 5.5 0 0 0 0-7.8Z'],
  close: ['m6 6 12 12M18 6 6 18'],
  refresh: ['M20 11a8 8 0 1 0 2 5', 'M20 5v6h-6'],
  check: ['m5 12 4 4L19 6'],
  shield: ['M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7l-9-4Z', 'm8 12 3 3 5-6'],
  compass: ['M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z', 'm16 8-2 6-6 2 2-6 6-2Z']
}
</script>
<template><svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="app-icon"><path v-for="(path,index) in (paths[name] || paths.spark)" :key="index" :d="path" /></svg></template>

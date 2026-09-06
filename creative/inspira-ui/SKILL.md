---
name: inspira-ui
description: Use when user wants inspira-ui animated Vue/Nuxt components.
license: MIT
---

# Inspira UI (unovue/inspira-ui)

shadcn 风格的 **Vue/Nuxt 动画组件库**（非 npm 包整体安装，而是**复制组件源码**进项目，类似 shadcn registry）。约 130+ 组件，12 大类，全部基于 Tailwind CSS v4 + motion-v + @vueuse/core。

## 何时使用

- 用户要 Vue/Nuxt 项目里的高级动画组件（按钮、卡片、文字、背景、光标、3D）
- 用户提到 inspira-ui、magic-ui、aceternity-ui 风格组件
- 需要即拷即用的 .vue 单文件组件

## 安装流程（Tailwind v4）

```bash
npm install @vueuse/core motion-v tw-animate-css @inspira-ui/plugins
```

1. 先装 Tailwind CSS v4（Vue 用 Vite 指南，Nuxt 用框架指南）
2. main.css 必须加 @theme inline 变量（组件依赖 --card/--primary/--radius 等 CSS 变量）——用"Other TailwindCSS Kit"模板（OKLCH 变量块）即可，不用 shadcn-vue 时跳过
3. 可选：Iconify Vue 图标支持（多数 demo 用到 <Icon>）
4. 到 https://inspira-ui.com/components 选组件，**复制 .vue 源码**进 `src/components/ui/`（及所需 demo 里用到的配套文件），按需加 CSS keyframes 到 main.css

注意：Tailwind v3 用户用旧版 v1 (v1.inspira-ui.com)，组件代码不兼容 v4 语法。

## 组件地图（12 类）

| 分类 | 组件 |
|---|---|
| backgrounds 背景 | aurora-background, black-hole, bubbles-bg, cosmic-portal, falling-stars, flickering-grid, interactive-grid-pattern, lamp-effect, liquid-background, neural-background, particles-bg, particle-whirlpool-bg, pattern-background, ripple, silk, singularity, snowfall-bg, sparkles, stars, stractium, tetris, thunderstorm, video-text, vortex, warp, wavy |
| buttons 按钮 | gradient-button, interactive-hover-button, rainbow-button, ripple-button, shimmer-button |
| cards 卡片 | 3d-card, apple-card-carousel, card-spotlight, direction-aware-hover, fey-cards, flip-card, floating-card, glare-card |
| cursors 光标 | fluid-cursor, image-trail-cursor, sleek-line-cursor, smooth-cursor, tailed-cursor |
| device-mocks 设备 | iphone-mockup, safari-mockup |
| input-and-forms 表单 | balance-slider, color-picker, file-upload, halo-search, input, placeholders-and-vanish-input |
| miscellaneous 杂项 | animated-circular-progressbar, animated-list, animated-modal, animated-tabs, animated-tooltip, animate-grid, bento-grid, book, compare, container-scroll, dock, expandable-gallery, images-slider, lens, link-preview, marquee, morphing-tabs, multi-step-loader, photo-gallery, scroll-island, shader-toy, svg-mask, timeline, tracing-beam |
| special-effects 特效 | animated-beam, border-beam, confetti, dither-shader, glow-border, glowing-effect, images-badge, meteors, neon-border, particle-image, progressive-blur, scales, scratch-to-reveal, spring-calendar |
| testimonials 口碑 | animated-testimonials, design-testimonials, testimonial-slider |
| text-animations 文字动画 | 3d-text, blur-reveal, box-reveal, colorful-text, container-text-flip, encrypted-text, flip-words, focus, hyper-text, letter-pullup, line-shadow-text, morphing-text, number-ticker, radiant-text, sparkles-text, spinning-text, text-generate-effect, text-glitch, text-highlight, text-hover-effect, text-reveal-card, text-reveal, text-scroll-reveal |
| visualization 可视化 | bending-gallery, carousal-3d, file-tree, github-globe, globe, icon-cloud, infinite-grid, light-speed, liquid-glass, liquid-logo, logo-cloud, logo-origami, orbit, spline, world-map |

## 典型用法示例

```vue
<!-- 波纹按钮 (ripple-button) -->
<script setup lang="ts">
import RippleButton from "@/components/ui/ripple-button/RippleButton.vue"
</script>
<template>
  <RippleButton ripple-color="#60a5fa" :duration="600">点击我</RippleButton>
</template>
```

关键点：
- 每个组件文档页有 `componentFiles` 列出需复制的配套 .vue 文件（如 RippleButton.vue + RippleButtonDemo.vue）
- 组件常有专属 CSS keyframes/变量，**必须**从文档 "instructions" 节复制进 main.css 的 `@theme inline`，否则动画不生效
- props/emits 见文档 API 表（如 ripple-button 有 class/rippleColor/duration props，click emit）

## 本地参考副本

仓库已 clone 在 `/tmp/inspira-ui`（含全部组件 demo 源码 `content/`、registry schema、中文文档 `content/cn/`）。写代码时可直接 `grep -r "组件名" /tmp/inspira-ui/content/en/2.components/` 找源码和说明。完整组件源码在官网页面可复制。

## 注意

- 只支持 Vue/Nuxt（v2 组件文档示例均为 `<script setup lang="ts">`）；React 用户用 magicui.design 原版
- 组件是 MIT 协议可自由使用
- 若项目没装 Tailwind v4，先升级或改用 v1 版组件

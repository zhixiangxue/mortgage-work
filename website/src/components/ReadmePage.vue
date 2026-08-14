<template>
  <SiteHeader />

  <div class="article-hero">
    <div class="shell-narrow">
      <div class="hero-eyebrow"><span class="dot"></span>README</div>
      <h1>Mortgage Work</h1>
      <p class="lede">一个会自己读文件、算数字、查规则的贷款官工作台。这一页说清楚三件事：这是什么、怎么装、怎么玩。</p>
      <div class="hero-contact">
        如有任何问题，欢迎联系我：<b>15658030236</b>（微信同号）
      </div>
    </div>
  </div>

  <main>
    <!-- 01 · 这是什么 / 解决什么问题 -->
    <section class="section">
      <div class="shell-narrow">
        <div class="section-head">
          <div class="section-eyebrow"><span class="dot"></span>01 · WHY</div>
          <h2>这是一个什么项目？</h2>
        </div>
        <BlogStory />
      </div>
    </section>

    <!-- 02 · 下载安装 + 配置 LLM -->
    <section class="section">
      <div class="shell-narrow">
        <div class="section-head">
          <div class="section-eyebrow"><span class="dot"></span>02 · SETUP</div>
          <h2>如何下载安装？如何配置 LLM？</h2>
        </div>
        <InstallSection />
      </div>
    </section>

    <!-- 03 · 怎么玩 -->
    <section class="section">
      <div class="shell-narrow">
        <div class="section-head">
          <div class="section-eyebrow"><span class="dot"></span>03 · PLAYBOOK</div>
          <h2>如何跑一个 case？</h2>
        </div>
        <PlaybookSection />
      </div>
    </section>

    <!-- 04 · 架构——只留一个引导，正文在独立的 Architecture 页 -->
    <section class="section">
      <div class="shell-narrow">
        <div class="section-head">
          <div class="section-eyebrow"><span class="dot"></span>04 · ARCHITECTURE</div>
          <h2>它是怎么搭起来的？</h2>
        </div>
        <p class="arch-blurb">
          五层结构、三个本地进程、一个 git 仓库。完整的系统设计写在了一个独立页面里：
          每一层做什么、层与层怎么接、边界划在哪里。评审前值得翻一遍。
        </p>
        <a class="arch-cta" href="index.html#architecture">
          打开 Architecture 页面
          <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M6 3l5 5-5 5"/>
          </svg>
        </a>
      </div>
    </section>

    <!-- 05 · DEMO 视频 -->
    <section class="section">
      <div class="shell-narrow">
        <div class="section-head">
          <div class="section-eyebrow"><span class="dot"></span>05 · DEMO</div>
          <h2>Mortgage Work 是怎么帮助LO工作的？</h2>
        </div>
        <div class="video-stack">
          <div v-for="n in demoCount" :key="n" class="video-item">
            <div class="video-cap"><span class="vnum">{{ String(n).padStart(2, '0') }}</span>DEMO {{ n }}</div>
            <div class="video-frame">
              <video :src="`https://wcbpub.oss-cn-hangzhou.aliyuncs.com/xue/goai/${n}.mp4`" controls preload="metadata"></video>
            </div>
          </div>
        </div>
      </div>
    </section>
  </main>

  <SiteFooter />
</template>

<script setup>
import SiteHeader from './SiteHeader.vue'
import SiteFooter from './SiteFooter.vue'
import BlogStory from './BlogStory.vue'
import InstallSection from './InstallSection.vue'
import PlaybookSection from './PlaybookSection.vue'

// Number of demo videos hosted on OSS (xue/goai/N.mp4)
const demoCount = 10
</script>

<style scoped>
.shell-narrow {
  max-width: 920px;
  margin: 0 auto;
  padding: 0 24px;
}

/* ===== Hero ===== */
.article-hero {
  position: relative;
  overflow: hidden;
  padding: 88px 0 56px;
}
.article-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(to right, rgba(60,215,66,0.12) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(60,215,66,0.12) 1px, transparent 1px);
  background-size: 48px 48px;
  -webkit-mask-image: radial-gradient(ellipse 100% 100% at 50% 30%, #000 10%, transparent 75%);
  mask-image: radial-gradient(ellipse 100% 100% at 50% 30%, #000 10%, transparent 75%);
  pointer-events: none;
  z-index: 0;
}
.article-hero .shell-narrow { position: relative; z-index: 1; }
.hero-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 700 10px var(--mono);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--brand);
  margin-bottom: 24px;
}
.hero-eyebrow .dot { width: 6px; height: 6px; background: var(--brand); }
.article-hero h1 {
  font: 700 46px/1.15 var(--sans);
  letter-spacing: -0.03em;
  margin-bottom: 18px;
}
.article-hero .lede {
  font-size: 18px;
  color: var(--text-2);
  line-height: 1.6;
  letter-spacing: -0.01em;
}
.hero-contact {
  margin-top: 28px;
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  font: 500 13px var(--mono);
  color: var(--text-2);
  border: 1px solid var(--border);
  background: var(--bg-panel);
  padding: 10px 14px;
}
.hero-contact b { color: var(--brand); font-weight: 700; }

/* ===== Sections ===== */
.section { padding: 48px 0; }
.section + .section { border-top: 1px solid var(--border); }
.section-head { margin-bottom: 32px; }
.section-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 700 10px var(--mono);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--brand);
  margin-bottom: 12px;
}
.section-eyebrow .dot { width: 6px; height: 6px; background: var(--brand); }
.section-head h2 {
  font: 700 32px/1.1 var(--sans);
  letter-spacing: -0.025em;
  margin-bottom: 10px;
}

/* ===== Architecture teaser ===== */
.arch-blurb {
  font-size: 16px;
  color: var(--text-2);
  line-height: 1.7;
  margin-bottom: 24px;
}
.arch-cta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font: 700 12px var(--mono);
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--brand);
  border: 1px solid var(--brand);
  padding: 12px 18px;
  transition: background .12s;
}
.arch-cta:hover { background: var(--tint-green); }

/* ===== Demo videos ===== */
.video-stack {
  display: flex;
  flex-direction: column;
  gap: 40px;
}
.video-item { display: flex; flex-direction: column; gap: 10px; }
.video-cap {
  display: flex;
  align-items: center;
  gap: 8px;
  font: 700 10px var(--mono);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--text-4);
}
.video-cap .vnum {
  color: var(--brand);
  background: var(--tint-green);
  padding: 2px 6px;
}
.video-frame {
  border: 1px solid var(--border-soft);
  background: var(--bg);
  box-shadow: 0 16px 48px rgba(0,0,0,0.4);
  line-height: 0;
}
.video-frame video {
  width: 100%;
  display: block;
  background: #000;
}

/* ===== Responsive ===== */
@media (max-width: 860px) {
  .article-hero h1 { font-size: 34px; }
  .section-head h2 { font-size: 26px; }
}
</style>

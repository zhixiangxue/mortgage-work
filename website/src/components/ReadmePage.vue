<template>
  <SiteHeader />

  <div class="article-hero">
    <div class="shell-narrow">
      <div class="hero-eyebrow"><span class="dot"></span>README</div>
      <h1>Mortgage Work</h1>
      <p class="lede">一款会自己读文件、算数字、查规则的贷款官 AI 办公软件。这一页说清楚三件事：这是什么、怎么装、怎么玩。</p>
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
        <div class="why-facts">
          <p class="why-facts-head">在往下读之前，有五件事必须先说清楚：</p>
          <ul>
            <li>这不是 demo——这是一个<b>真实的项目</b>。</li>
            <li>它正在解决美国房贷行业<b>真实存在的问题</b>。</li>
            <li>它的部分功能，正在<b>服务美国房贷行业的数千位真实LO客户</b>。</li>
            <li>它是一款可能在<b>数月内投放美国市场</b>的 AI 办公产品。</li>
            <li>而在这件事里，<b>中国的国产大模型可能正在发挥重要作用</b>——没有别的原因，就是靠实力：它们出色的性能与极致的性价比，是这类 AI 办公产品真正能落地、能商用的关键。</li>
          </ul>
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

    <!-- 06 · 彩蛋——压轴：Fannie Mae 在和我们合作，先让评审看懂它是什么分量 -->
    <section class="section">
      <div class="shell-narrow">
        <div class="section-head">
          <div class="section-eyebrow"><span class="dot"></span>06 · EASTER EGG</div>
          <h2>最后，一个彩蛋</h2>
        </div>
        <div class="fnma-panel">
          <p class="fnma-headline"><b>Fannie Mae（房利美）正在和我们合作。</b></p>
          <p class="fnma-sub">如果你对美国房贷行业不熟，可能意识不到这句话的分量——它成立于 1938 年罗斯福新政时期，是美国房贷体系近 90 年的基石：</p>
          <div class="fnma-stats">
            <div class="fnma-stat">
              <span class="fnma-num">No.50</span>
              <span class="fnma-cap">2025《财富》世界 500 强，年营收超 $150B</span>
            </div>
            <div class="fnma-stat">
              <span class="fnma-num">~$3.2T</span>
              <span class="fnma-cap">担保的房贷规模——美国每四笔住房贷款，就有一笔由它担保</span>
            </div>
            <div class="fnma-stat">
              <span class="fnma-num">$3T+</span>
              <span class="fnma-cap">它发行的债券，被全球数十个国家的央行与主权基金作为准美国主权资产持有</span>
            </div>
          </div>
          <p class="fnma-sub">它编写的 <b>Selling Guide</b> 是美国标准房贷（conforming loan）事实上的审核法典，全美贷款官都要照着它做事——前面玩法里被拖进 AI 面板的那份 PDF，正是出自它手。</p>
          <p class="fnma-outro">现在，写规则的人，正在和我们一起探索 AI 贷款官的下一步。</p>
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
.why-facts {
  border: 1px solid var(--border);
  border-left: 3px solid var(--brand);
  background: var(--bg-panel);
  padding: 24px 28px;
  margin-bottom: 32px;
}
.why-facts-head {
  font: 700 13px var(--mono);
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--brand);
  margin-bottom: 16px;
}
.why-facts ul { display: flex; flex-direction: column; gap: 12px; }
.why-facts li {
  position: relative;
  padding-left: 22px;
  font-size: 16.5px;
  line-height: 1.7;
  color: var(--text);
}
.why-facts li::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 11px;
  width: 8px;
  height: 8px;
  background: var(--brand);
}
.why-facts li b { color: var(--brand); }

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

/* ===== Fannie Mae easter egg ===== */
.fnma-panel {
  border: 1px solid var(--border);
  border-top: 2px solid var(--brand);
  background: var(--bg-panel);
  padding: 32px;
}
.fnma-headline { font-size: 20px; line-height: 1.5; margin-bottom: 12px; }
.fnma-headline b { color: var(--brand); }
.fnma-sub { font-size: 15px; color: var(--text-2); line-height: 1.8; }
.fnma-sub b { color: var(--text); }
.fnma-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  margin: 24px 0;
}
.fnma-stat {
  background: var(--bg-panel);
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.fnma-num { font: 700 24px var(--mono); color: var(--brand); letter-spacing: -0.02em; white-space: nowrap; }
.fnma-cap { font-size: 13px; color: var(--text-3); line-height: 1.6; }
.fnma-outro {
  margin-top: 24px;
  padding-left: 12px;
  border-left: 2px solid var(--brand);
  font-size: 16px;
  font-weight: 500;
  line-height: 1.7;
}

/* ===== Responsive ===== */
@media (max-width: 860px) {
  .article-hero h1 { font-size: 34px; }
  .section-head h2 { font-size: 26px; }
  .fnma-stats { grid-template-columns: 1fr; }
  .fnma-panel { padding: 20px; }
}
</style>

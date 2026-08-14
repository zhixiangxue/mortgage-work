<template>
  <div>
    <p class="pb-intro">
      预置的工作仓库里已经有 8 个客户档案和 5 家机构（Fannie Mae / iTrust / JMAC / MC Funding / NewWave）的真实产品文档。
      不需要造数据，挑一个玩就行 —— 下面两个是最直观的例子。
    </p>

    <div class="case">
      <div class="case-head">
        <span class="case-num">01</span>
        <span class="case-title">查 Guideline：把产品文档扔给它，直接问</span>
      </div>
      <div class="case-steps">
        <div class="case-step">
          <span class="cs-num">a</span>
          <span>在左侧产品库找到 <code>products/FennieMae/Selling-Guide_06-03-2026_highlighted.pdf</code>，把它拖进右侧 AI 面板。</span>
        </div>
        <div class="case-step">
          <span class="cs-num">b</span>
          <span>问它：</span>
        </div>
        <div class="case-q">“比特币可以作为资产么？”</div>
        <div class="case-step">
          <span class="cs-num">c</span>
          <span>它会去读这份几百页的 Selling Guide，给出答案 —— 并且附上原文出处，点引用就能跳回 PDF 里那一页，自己核对。</span>
        </div>
      </div>
    </div>

    <div class="case">
      <div class="case-head">
        <span class="case-num">02</span>
        <span class="case-title">盘客户：这个案子还缺什么资料？</span>
      </div>
      <div class="case-steps">
        <div class="case-step">
          <span class="cs-num">a</span>
          <span>打开客户 <code>chang</code> —— 一个自雇 borrower，手里有几张 1099 和一份 CPA 损益表。</span>
        </div>
        <div class="case-step">
          <span class="cs-num">b</span>
          <span>在 AI 面板里问：</span>
        </div>
        <div class="case-q">“这个客户还缺什么资料？”</div>
        <div class="case-step">
          <span class="cs-num">c</span>
          <span>它会把文件夹里已有的材料挨个读一遍（1099、银行流水、信用报告、购房合同……），对照贷款要求告诉你还缺什么 —— 比如两年的 tax return。这正是每个 LO 接案后要花 1-2 天干的事。</span>
        </div>
      </div>
    </div>

    <p class="pb-outro">
      剩下的客户（<code>chen-wei-liu</code>、<code>mendez</code>、<code>daniel-grace-okafor</code>……）都是完整档案，随便挑一个，
      让它算收入、核 DTI、匹配产品 —— 想怎么问就怎么问。
    </p>
  </div>
</template>

<style scoped>
.pb-intro, .pb-outro {
  font-size: 15px;
  line-height: 1.85;
  color: var(--text-2);
}
.pb-intro { margin-bottom: 28px; }
.pb-outro { margin-top: 28px; }
.pb-intro code, .pb-outro code, .case-step code {
  font: 400 12.5px var(--mono);
  color: var(--text);
  background: var(--bg-panel);
  border: 1px solid var(--border);
  padding: 1px 6px;
}
.case {
  border: 1px solid var(--border-soft);
  background: var(--wash-brand);
  padding: 22px 24px;
}
.case + .case { margin-top: 20px; }
.case-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}
.case-num {
  font: 700 10px var(--mono);
  letter-spacing: 1px;
  color: var(--brand);
  background: var(--tint-green);
  padding: 3px 6px;
  flex-shrink: 0;
}
.case-title {
  font: 700 17px var(--sans);
  letter-spacing: -0.01em;
  color: var(--text);
}
.case-steps { display: flex; flex-direction: column; gap: 10px; }
.case-step {
  display: flex;
  gap: 10px;
  font-size: 14.5px;
  line-height: 1.8;
  color: var(--text-2);
}
.cs-num {
  flex-shrink: 0;
  font: 700 11px var(--mono);
  color: var(--text-4);
  width: 16px;
  text-align: center;
  padding-top: 3px;
}
.case-q {
  margin: 2px 0 2px 26px;
  padding: 10px 14px;
  border-left: 2px solid var(--brand);
  background: var(--bg-panel);
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}
</style>

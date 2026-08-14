<template>
  <div class="story">
    <p class="big-fact">美国房贷市场——全球除美国国债之外，最大的债务市场。</p>

    <p>超过 13 万亿美元的存量规模，接近中国一年 GDP 的七成。每年新增房贷 1.5 到 4 万亿美元，取决于利率环境和经济周期。</p>

    <p>大到什么程度？大到全球的央行——几乎都在持有美国的房贷债券。大到美联储自己的资产负债表上，趴着超过 2 万亿美元的 Agency MBS。大到这个市场稍微抖一下，2008 年全世界跟着一起塌。</p>

    <p><strong>但推动这一切的那个角色——那个决定到底给谁放款、放多少、按什么条件放的贷款官（Loan Officer，简称LO）——他今天的工作方式，跟 2、30 年前几乎没有任何区别。</strong></p>

    <p>事实就是如此，你别笑...</p>

    <p>一个贷款官的日常是这样的——客户来了，收文件。W-2、银行流水、信用报告、税单、购房合同，少则十几份，几十上百页那是司空见惯的。然后一项项看，一个个数字对，掏计算器算，翻各家贷款机构的文档查产品规则，凭经验判断能做什么贷款。从接案到出大致方向，一个资深的贷款官也要花1-2天才能大概捋清楚头绪。而一笔贷款从开始到结束，一般需要2个月左右。</p>

    <p>美国有几十万贷款官。几乎所有人，每天都在重复这套流程。没有 AI。没有自动化。甚至没有一个像样的工作台——绝大多数人还是靠文件管理器 + PDF 阅读器 + 计算器在干活。对，这就是一个智力+劳动密集型的行业。这类行业还有一个类似的——程序员。而就在一年多以前，Coding Agent 彻底改变了程序员的工作习惯，也造就了 Anthropic 这样的巨头横空出世。</p>

    <p class="lead-in"><strong>为什么是现在？</strong></p>

    <p>全球经济低迷，利率居高不下，refi 这种高毛利的生意不好做，purchase 这种常规业务又在萎缩。市场现实摆在那儿，没有足够多、足够有经验的LO你的生意根本维系不下去。但一个资深的 LO 培养起来要几年，市场上根本没有那么多有经验的人 —— 你想培养？等不起，你想加人？也找不到。堆人堆不出产能，但除了堆人你又能怎么办？利率越高，这个行业的结构性矛盾就越尖锐。</p>

    <p>怎么办？</p>

    <p>今天，我想给你看一个不同的答案。</p>

    <hr />

    <p>LO本质上来说就是一个中介，通过撮合贷款人和贷款机构来获利。听起来好像很简单，但是，美国的放贷行业是一个规则非常细的行业，细到什么程度呢？我们来粗算一笔账：</p>

    <ul>
      <li>贷款产品维度：QM 自住 / FHA / VA / USDA / Jumbo / DSCR / Bank Statement / 1099 / P&amp;L / Asset Depletion / HELOC / Cash-Out / Commercial / Hard Money / Reverse / Construction... 大约 15-20 条主线</li>
      <li>贷款人维度：W-2 雇员 / 自雇 Sole Prop / 自雇 S-Corp / 合伙人 / 退休 / 高净值 / 外籍 / 信用修复 / 多套房主... 大约 8-10 类</li>
      <li>贷款标的维度：自住 / 二居 / 1-4 单元投资 / 5+ 多户 / 商业办公 / 零售 / 工业 / 土地 / 翻修中... 大约 8-9 类</li>
    </ul>

    <p>粗乘：20 × 10 × 9 ≈ 1800 种理论组合。</p>

    <p>而且，你要知道，美国是一个金融行业非常发达的国家，你以为房贷只是“借钱买房子”的么？不不不，房子在美国是一种资产，是资产就可以盘活，所以大量的金融玩法（比如refi的各种贷款）在里面就会让这个游戏变得异常复杂，更别谈二级衍生品市场了...</p>

    <p>那么，是哪些事情让LO最头疼、最限制产能的呢？我在这里梳理了一个"5宗最"：</p>

    <div class="most"><span class="idx">01</span>第一最：文档处理。</div>

    <p>这是每一个LO每天睁眼就要面对的事。客户的W-2、银行流水、税单、信用报告、购房合同……少则十几份，多则上百页。没有两个人的W-2长得一样，没有两家银行的流水排版相同。这些文档高度个性化、完全非结构化，以前你想用程序自动处理？做梦。OCR扫出来一堆乱码，模板匹配换一个格式就崩。所以LO只能一份份看，一行行对，一个数字一个数字地抄。这是整个流程里最枯燥、最耗时的环节，没有之一。</p>

    <p>但这件事，恰恰是LLM最擅长的。大语言模型的核心能力就是从非结构化文本中理解语义、提取信息。几百页文件扔进去，它能在几十秒内告诉你：这个borrower过去两年收入分别是多少、哪张卡上每月固定支出异常、税表里有没有漏报的1099收入。不是关键词匹配，而是真正的理解。这在以前是不可能的。</p>

    <div class="most"><span class="idx">02</span>第二最：数字计算。</div>

    <p>DTI、LTV、CLTV、收入折算、资产验证、贷款月供……这些计算的规则是死的，但每次都要重新算。自雇borrower的收入怎么折？RSU算不算？多套出租房的正现金流怎么加？一个数字算错，后面的判断全歪。更恶心的是，不同产品、不同机构对同一个指标的计算口径还不一样——FHA算DTI的方式和Jumbo不一样，Fannie Mae和Freddie Mac对自雇收入的处理也有差异。</p>

    <p>AI在这里的价值不是"算得快"，而是"算不错"。规则引擎 + LLM的组合，可以把计算逻辑写成可审计的步骤，每一步都能追溯到原始文件里的具体数字。LO不需要再掏计算器了，更不需要担心自己少加了一笔租金收入或者多除了一个月。</p>

    <div class="most"><span class="idx">03</span>第三最：Guideline 查询。</div>

    <p>每一个贷款机构都有一套自己的产品规则，动辄几百页PDF。Fannie Mae的Selling Guide、Freddie Mac的Seller/Servicer Guide、FHA的Single Family Handbook……这还只是Agency层面。加上Non-QM lender各自的产品矩阵，一个LO理论上需要掌握的信息量，堪比一个中型律所的执业律师。</p>

    <p>现实是什么呢？绝大多数LO只熟悉自己常做的那三五款产品。遇到不熟的case，要么翻PDF翻到怀疑人生，要么凭印象赌一把——赌错了，underwriting阶段被打回来，时间白费，客户跑掉。</p>

    <p>LLM + RAG + Knowledge Graph + Source Doc，这几样东西组合在一起，把guideline从"一本翻不动的死书"变成"一个可以对话的活系统"。LO不需要记任何东西，他只需要问："自雇borrower，用Bank Statement产品，信用分680，能做吗？要什么条件？"系统会告诉他答案——引用原文，标出来源，甚至可以告诉他："这个条件在FHA那边更宽松，要不要看看？"一个LO，理论上可以代理全美的产品。这在以前想都不敢想。</p>

    <div class="most"><span class="idx">04</span>第四最：复杂案件判断。</div>

    <p>W-2雇员、一套自住房、信用分750——这种case谁都能做。但自雇borrower呢？有多套投资房、每套都有租金收入和折旧抵扣的呢？有1099收入但没有两年tax return的呢？这些复杂case，以前只有top LO能接。一个top LO和一个普通LO，差别不在勤奋，在经验——他见过足够多的case，踩过足够多的坑，知道什么能做什么不能做。</p>

    <p>但经验这东西，本质上就是"模式识别 + 规则匹配"——这又是AI的强项。通过skill和sub-agent的机制，你可以把top LO的经验拆成一个个可复用的判断模块：收入分析agent、资产核算agent、信用评估agent、DTI计算agent、LTV核算agent、产品匹配agent……一个资历浅的LO，不再需要自己积累十年经验才能碰复杂case。他只需要把case拆开，让对应的agent来处理，然后看综合结论。<strong>Mortgage Work之于LO，就是Cursor之于程序员。</strong></p>

    <div class="most"><span class="idx">05</span>第五最：产品匹配。</div>

    <p>还记得前面那个1800种组合吗？现实比这更残酷——每家lender的产品矩阵都不同，利率每天都在变，同一个borrower在A机构只能做FHA，在B机构能做Conventional而且利率更低。但LO是人，人只能"知道自己知道的"。一个LO通常只跟3-5家lender深度合作，他能推荐的产品，最多就是他脑子里那十几个。不是不想给客户最好的，是他根本不知道还有更好的存在。</p>

    <p>AI在这里的优势是压倒性的——它可以同时"知道"所有产品、所有guideline、所有利率，然后对每一个borrower做全空间搜索。1800种组合也就是秒级的事，而且它会告诉你为什么推荐这个产品，依据是哪一条guideline，利率比替代方案低多少bp。这不再是"我熟悉的里面哪个合适"，而是"全市场最优解是什么"，这在之前根本是不可能的事情。</p>

    <hr />

    <p>五件事说完了。你会发现：这些事情都是非标的、费时费力的、极度容易出错的、高度依赖经验和耐心的事情，LO的工作大部分时间都是花费在这些事情上面的 —— 这就是 Mortgage Work 要解决的事。下面说清楚：怎么装，怎么配，怎么玩。</p>
  </div>
</template>

<style scoped>
.story p {
  font-size: 16px;
  line-height: 1.9;
  color: var(--text-2);
  margin-bottom: 22px;
}
.story p strong { color: var(--text); font-weight: 700; }
.story hr {
  border: 0;
  border-top: 1px solid var(--border);
  margin: 48px 0;
}
.story ul {
  margin: 0 0 22px;
  padding-left: 2px;
  list-style: none;
}
.story ul li {
  position: relative;
  padding-left: 20px;
  font-size: 15px;
  line-height: 1.85;
  color: var(--text-2);
  margin-bottom: 8px;
}
.story ul li::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 12px;
  width: 6px;
  height: 6px;
  background: var(--brand);
}
.story .lead-in {
  font-size: 17px;
  color: var(--text);
}
.story .big-fact {
  font-size: 17px;
  color: var(--text);
  font-weight: 600;
}
/* "X宗最" item headings */
.most {
  display: flex;
  align-items: center;
  gap: 10px;
  font: 700 20px var(--sans);
  letter-spacing: -0.02em;
  color: var(--text);
  margin: 44px 0 16px;
}
.most .idx {
  font: 700 10px var(--mono);
  letter-spacing: 1px;
  color: var(--brand);
  background: var(--tint-green);
  padding: 3px 6px;
  flex-shrink: 0;
}
</style>

// Hy3 Research Studio — frontend (vanilla JS, no build step)
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const state = {
  taskId: null,
  uploads: [],
  sources: {},
  packets: [],
  sections: {},
  pendingSources: [],   // 来自文库/文献检索、将带入研究的资料
  currentTool: "abstract",
  searchMode: "normal", // normal | smart
  litResults: [],        // 普通检索累计结果（支持加载更多）
  litPage: 1,
  litQuery: "",
  paperId: null,         // 当前研讨的论文 id
  paperHistory: [],      // 论文研讨多轮对话
  advisorHistory: [],    // 思路提炼多轮对话
  advisorGuideMd: "",   // 最近一次生成的提炼指南（Markdown）
  intentLocked: false,   // 用户已手动选择，停止自动套用意图识别
  _intentTimer: null,
  // 创造工坊
  featureList: [],
  featureFavs: [],
  featureChatId: null,
  featureHistory: [],
  featureMode: "simple",
  featureBlocks: [],
  _nfPreview: null,       // 当前生成的未保存功能（一句话级别）
  _nfLevel: "simple",
  _nfChat: [],            // 初步设计：设计对话历史
  _nfDesign: null,        // 初步设计：生成的功能
  _nfDesignLayout: [],    // 初步设计：当前布局（可拖拽顺序）
  // 反馈看板
  feedbackItems: [],
  feedbackCloud: [],
  _cloudBoxes: [],
  _fbCat: "功能建议",
  _fbFilter: null,
  _fbSort: "up",
  _fbUpvoted: {},
};

// ---------- theme ----------
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const label = document.querySelector("#themeToggle .theme-label");
  if (label) label.textContent = theme === "light" ? "深色模式" : "浅色模式";
}
function initTheme() {
  const saved = localStorage.getItem("hy3-theme") || "dark";
  applyTheme(saved);
  const btn = $("#themeToggle");
  if (btn) btn.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
    localStorage.setItem("hy3-theme", next);
    applyTheme(next);
  });
}

// ---------- model status（右侧栏"模型状态"共享，左下角徽标已移除） ----------
let _modelInfo = { text: "检测中…", cls: "muted" };
function updateModelStatus(text, cls) {
  _modelInfo = { text, cls };
  const rm = $("#rrModel");
  if (rm) { rm.textContent = text; rm.className = "rr-model " + cls; }
}

// ---------- init ----------
initTheme();
init();
async function init() {
  try {
    const r = await fetch("/api/health");
    const h = await r.json();
    if (h.configured) updateModelStatus(`● ${h.model}`, "ok");
    else updateModelStatus("未配置 API Key", "err");
  } catch {
    updateModelStatus("后端未连接", "err");
  }
  bindGlobal();
  await Promise.all([loadSettings(), renderLibrary(), renderHistory(), loadSuggestions(), renderRightRail(), loadResearchHome()]);
  // 独立功能工作空间（方案 §8）：直接访问 /feature/{id} 进入专属界面
  const pm = location.pathname.match(/^\/feature\/([^/]+)\/?$/);
  if (pm) {
    fwState.standalone = true;
    enterFeatureWorkspace(pm[1]);
    return;
  }
  // 独立功能工作空间（方案 §8）：#/feature/{id} 进入专属界面
  handleHashRoute();
}

function bindGlobal() {
  $$(".nav-item").forEach((b) =>
    b.addEventListener("click", () => switchView(b.dataset.view))
  );
  // research setup
  $$(".chip[data-ex]").forEach((b) =>
    b.addEventListener("click", () => {
      $("#queryInput").value = b.dataset.ex;
      state.intentLocked = false;
      hideIntentBanner();
      detectIntent();
    })
  );
  $("#queryInput").addEventListener("input", () => {
    state.intentLocked = false;
    clearTimeout(state._intentTimer);
    state._intentTimer = setTimeout(detectIntent, 700);
  });
  // 用户手动改选项 → 锁定自动套用，避免被意图识别覆盖
  ["#taskType", "#style", "#depth", "#language"].forEach((sel) =>
    $(sel).addEventListener("change", () => { state.intentLocked = true; hideIntentBanner(); updateHint(); }));
  $("#startBtn").addEventListener("click", startResearch);
  $("#depth").addEventListener("change", updateHint);
  $("#citeCount").addEventListener("input", updateHint);
  $("#citeCount").addEventListener("change", updateHint);
  $("#fileInput").addEventListener("change", handleUpload);
  $("#newResearchBtn").addEventListener("click", () => {
    $("#researchWorkspace").classList.add("hidden");
    openFlowModal("新建研究", $("#researchSetup"));
  });
  $$("#researchWorkspace .tab").forEach((t) =>
    t.addEventListener("click", () => switchTab(t.dataset.tab))
  );
  // literature search
  $("#litSearchBtn").addEventListener("click", () => runSearch());
  $("#litQuery").addEventListener("keydown", (e) => { if (e.key === "Enter") runSearch(); });
  $("#litSelectAll").addEventListener("change", (e) =>
    $$("#litResults .lit-card").forEach((c) => (c.querySelector("input").checked = e.target.checked)));
  $("#litToResearch").addEventListener("click", litToResearch);
  $("#litSaveSel").addEventListener("click", litSaveSel);
  $("#loadMoreBtn").addEventListener("click", loadMore);
  $$(".mode-btn").forEach((b) => b.addEventListener("click", () => switchSearchMode(b.dataset.mode)));
  // paper discussion
  $("#paperUploadBtn").addEventListener("click", paperUpload);
  $("#paperFile").addEventListener("change", paperUpload);
  $("#paperSendBtn").addEventListener("click", paperSend);
  $("#paperInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); paperSend(); }
  });
  $("#paperNewBtn").addEventListener("click", () => {
    state.paperId = null; state.paperHistory = [];
    $("#paperFile").value = "";
    $("#paperStatus").textContent = "支持 .pdf / .txt / .md；解析在本地服务端完成，全文用于本次研讨。";
    $("#paperChat").classList.add("hidden");
    $("#paperEmpty").classList.remove("hidden");
  });
  $("#paperDeleteBtn").addEventListener("click", async () => {
    if (!state.paperId) return toast("当前没有可删除的研讨记录", true);
    if (!confirm("确定删除这条研讨记录？当前对话将一并清空。")) return;
    try {
      await fetch("/api/paper/history/" + encodeURIComponent(state.paperId), { method: "DELETE" });
      state.paperId = null; state.paperHistory = [];
      $("#paperFile").value = "";
      $("#paperStatus").textContent = "支持 .pdf / .txt / .md；解析在本地服务端完成，全文用于本次研讨。";
      $("#paperChat").classList.add("hidden");
      $("#paperEmpty").classList.remove("hidden");
      toast("已删除研讨记录");
      renderRightRail();
    } catch (e) { toast("删除失败", true); }
  });
  $$("#paperStarters .chip").forEach((b) =>
    b.addEventListener("click", () => { $("#paperInput").value = b.dataset.q; $("#paperInput").focus(); }));
  $("#paperCopyBtn").addEventListener("click", copyPaperChat);
  // library
  $("#libSelectAll").addEventListener("change", (e) => {
    $$("#libList .lib-card").forEach((c) => (c.querySelector("input").checked = e.target.checked));
    updateLibCount();
  });
  $("#libToResearch").addEventListener("click", libToResearch);
  $("#libUploadBtn").addEventListener("click", () => $("#libFile").click());
  $("#libFile").addEventListener("change", libUpload);
  $("#libMoveBtn").addEventListener("click", openLibMoveModal);
  // 移动弹窗
  $("#libMoveModalClose").addEventListener("click", closeLibMoveModal);
  $("#libMoveCancel").addEventListener("click", closeLibMoveModal);
  $("#libMoveConfirm").addEventListener("click", confirmLibMove);
  $("#libMoveModal").addEventListener("click", (e) => { if (e.target.id === "libMoveModal") closeLibMoveModal(); });
  $("#libNewFolder").addEventListener("click", () => {
    // 在当前选中的真实文件夹下新建子文件夹；选中"全部/未分类"则在根目录新建
    const pid = libActiveIsReal() ? libActiveFolder : "";
    openNewFolderModal(pid);
  });
  $("#libRenFolder").addEventListener("click", () => {
    if (!libActiveIsReal()) return toast("请先在左侧选择一个文件夹", true);
    renFolder(libActiveFolder, libActiveFolderName());
  });
  $("#libDelFolder").addEventListener("click", () => {
    if (!libActiveIsReal()) return toast("请先在左侧选择一个文件夹", true);
    delFolder(libActiveFolder, libActiveFolderName());
  });
  // 新建文件夹弹窗
  $("#libFolderModalClose").addEventListener("click", closeNewFolderModal);
  $("#libFolderModal").addEventListener("click", (e) => { if (e.target.id === "libFolderModal") closeNewFolderModal(); });
  $("#libFolderCancel").addEventListener("click", closeNewFolderModal);
  $("#libFolderOk").addEventListener("click", createFolder);
  $("#libFolderName").addEventListener("keydown", (e) => { if (e.key === "Enter") createFolder(); });
  // studio（工具列表由 JS 动态渲染）
  renderStudioTools();
  $("#studioRun").addEventListener("click", runTool);
  // settings
  $("#saveSettingsBtn").addEventListener("click", saveSettings);
  // profile（个人主页）
  $("#pfSave").addEventListener("click", saveProfile);
  $("#pfInterestAdd").addEventListener("click", () => { addInterest($("#pfInterestInput").value); $("#pfInterestInput").value = ""; });
  $("#pfInterestInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); addInterest(e.target.value); e.target.value = ""; }
  });
  $("#pfInterests").addEventListener("click", (e) => {
    const b = e.target.closest(".pf-tag-x"); if (b) removeInterest(b.dataset.v);
  });
  $("#pfInterestSuggest").addEventListener("click", (e) => {
    const c = e.target.closest(".pf-preset"); if (c) addInterest(c.dataset.v);
  });
  $("#pfAvatarPick").addEventListener("click", (e) => {
    const a = e.target.closest(".pf-av-opt"); if (!a) return;
    pfAvatar = a.dataset.v; renderAvatar(); renderProfileAvatars();
  });
  $("#pfAvatarUploadBtn").addEventListener("click", () => $("#pfAvatarFile").click());
  $("#pfAvatarFile").addEventListener("change", (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    if (f.size > 2 * 1024 * 1024) return toast("图片过大，请选择 2MB 以内的图片", true);
    const reader = new FileReader();
    reader.onload = () => { pfAvatar = reader.result; renderAvatar(); renderProfileAvatars(); };
    reader.readAsDataURL(f);
  });
  // library filter
  $("#libSearch").addEventListener("input", renderLibFiltered);
  $("#libType").addEventListener("change", renderLibFiltered);
  $("#libSort").addEventListener("change", renderLibFiltered);
  $("#libFilterBtn").addEventListener("click", () => $("#libFilterPop").classList.toggle("hidden"));
  $("#libFilterClose").addEventListener("click", () => $("#libFilterPop").classList.add("hidden"));
  initLibResizer();
  // literature search: 年份过滤 / 排序立即生效
  $("#litYear").addEventListener("change", () => { if (state.litQuery) doSearch(); });
  $("#litSort").addEventListener("change", applyLitSort);
  // history module filter
  $$("#histFilter .hf").forEach((b) => b.addEventListener("click", () => {
    $$("#histFilter .hf").forEach((x) => x.classList.toggle("active", x === b));
    renderHistoryList(b.dataset.kind);
  }));
  // history: 选择删除
  $("#histSelectBtn").addEventListener("click", toggleHistSelMode);
  $("#histCancelSel").addEventListener("click", toggleHistSelMode);
  $("#histSelectAll").addEventListener("change", (e) => histSelectAll(e.target.checked));
  $("#histDelSel").addEventListener("click", histDelSelected);

  // ===== 通用弹窗（窗口）与折叠流程 =====
  $("#modalClose").addEventListener("click", closeFlowModal);
  $("#flowModal").addEventListener("click", (e) => { if (e.target.id === "flowModal") closeFlowModal(); });
  $("#citePopClose").addEventListener("click", () => $("#citePop").classList.add("hidden"));
  $("#citePop").addEventListener("click", (e) => { if (e.target.id === "citePop") $("#citePop").classList.add("hidden"); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeFlowModal();
      $("#citePop").classList.add("hidden");
      $("#featureModal").classList.add("hidden");
      $("#newFeatureModal").classList.add("hidden");
      $("#guideModal").classList.add("hidden");
      closeNewFolderModal();
      $("#libFilterPop").classList.add("hidden");
      closeLibMoveModal();
    }
  });
  // 深度研究：配置以窗口方式打开（按钮在中间空状态卡片）
  $("#researchEmptyBtn").addEventListener("click", () => openFlowModal("新建研究", $("#researchSetup")));
  // 使用指南弹窗（内容随当前页面变化；按钮为单例，由 JS 注入到当前页头部右上角并随页面滚动）
  $("#guideClose").addEventListener("click", () => $("#guideModal").classList.add("hidden"));
  $("#guideModal").addEventListener("click", (e) => { if (e.target.id === "guideModal") $("#guideModal").classList.add("hidden"); });

  // 各页面的使用指南内容（GUIDE 与 openGuide 已在文件顶层定义，供 ensureGuideBtn / switchView 共享）
  // 初始化时把单例指南按钮注入到默认（当前）页面的头部右上角
  placeGuideInHead(currentView);
  // 论文研讨：中间按钮直接选文件；支持从文库选择 PDF
  $("#paperEmptyBtn").addEventListener("click", () => $("#paperFile").click());
  $("#paperFromLibBtn").addEventListener("click", openPaperLibPicker);

  // 检索筛选弹层 + 推荐
  bindFilterPopover();
  updateFilterChips();
  loadRecommendations();  // 预加载首页推荐，进入检索页即有内容

  // 复制增强：所有生成内容可复制（表格/代码单一复制 + .md 导出）
  initCopyEnhance();
  $("#smartDownloadHtml").addEventListener("click", () => downloadHtml($("#smartReport"), "检索报告.html"));
  $("#smartCopyMd").addEventListener("click", onSmartCopyMd);
  $("#smartCopyTxt").addEventListener("click", () => copyNode($("#smartReport")));
  $("#researchCopyBtn").addEventListener("click", () => copyNode($("#report")));
  $("#studioCopyBtn").addEventListener("click", () => copyText(state.studioMd || "", $("#studioCopyBtn")));

  // 创造工坊：绑定
  $("#newFeatureBtn").addEventListener("click", openNewFeature);
  $("#forgeCreatorBtn").addEventListener("click", () => switchForgeScope("creator"));
  $("#newFeatureClose").addEventListener("click", () => $("#newFeatureModal").classList.add("hidden"));
  $("#newFeatureModal").addEventListener("click", (e) => { if (e.target.id === "newFeatureModal") $("#newFeatureModal").classList.add("hidden"); });
  $("#nfGenerate").addEventListener("click", generateFeature);
  $("#nfChatSend").addEventListener("click", nfDesignSend);
  $("#nfChatInput").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); nfDesignSend(); } });
  $("#nfBuild").addEventListener("click", nfBuild);
  $("#featSearch").addEventListener("input", () => {
    clearTimeout(state._featTimer);
    state._featTimer = setTimeout(() => loadFeatures($("#featSearch").value.trim()), 250);
  });
  $("#forgeSort").addEventListener("change", () => { loadFeatures($("#featSearch").value.trim()); });
  $$("#forgeSubtabs .forge-tab").forEach((t) =>
    t.addEventListener("click", () => switchForgeScope(t.dataset.scope)));
  $$("#builderModeSelect .builder-mode-card").forEach((c) =>
    c.addEventListener("click", () => switchBuilderMode(c.dataset.level)));
  $$(".bp-chip").forEach((c) =>
    c.addEventListener("click", () => { $("#nfDesc").value = c.dataset.q; }));
  $("#featureModalClose").addEventListener("click", () => {
    if (state.featureStandalone) { location.href = "/"; return; }
    $("#featureModal").classList.add("hidden");
  });
  $("#featureModal").addEventListener("click", (e) => {
    if (e.target.id === "featureModal") {
      if (state.featureStandalone) { location.href = "/"; return; }
      $("#featureModal").classList.add("hidden");
    }
  });

  // ===== Feature Workspace 独立工作区工具栏绑定 =====
  $("#fwBackBtn").addEventListener("click", exitFeatureWorkspace);
  $("#fwFavBtn").addEventListener("click", () => {
    if (!fwState.feature) return;
    featureToggleFav(fwState.feature.id);
    $("#fwFavBtn").classList.toggle("active");
  });
  $("#fwForkBtn").addEventListener("click", () => {
    if (!fwState.feature) return;
    featureFork(fwState.feature.id);
  });
  $("#fwInfoBtn").addEventListener("click", toggleFeatureInfo);
  $("#fwInfoClose").addEventListener("click", () => $("#fwInfoPanel").classList.add("hidden"));

  // Chat布局发送按钮
  $("#fwSendBtn").addEventListener("click", () => {
    const inp = $("#fwChatInput");
    if (inp.value.trim()) { sendFwChat(inp.value.trim()); inp.value = ""; }
  });
  $("#fwChatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#fwSendBtn").click(); }
  });
  $("#fwChatStarters").addEventListener("click", (e) => {
    const chip = e.target.closest(".res-starter-chip");
    if (chip) sendFwChat(chip.dataset.starter || chip.textContent);
  });

  // 反馈看板：绑定
  $("#fbSubmit").addEventListener("click", fbSubmit);
  $("#fbClearFilter").addEventListener("click", () => {
    state._fbFilter = null; $("#fbClearFilter").classList.add("hidden"); renderFbList();
  });
  const fbSortEl = $("#fbSort");
  if (fbSortEl) fbSortEl.addEventListener("change", () => { state._fbSort = fbSortEl.value; renderFbList(); });
  const fbCanvas = $("#fbCloud");
  fbCanvas.addEventListener("click", (e) => {
    const b = fbCloudHit(e);
    if (b) { state._fbFilter = b.text; renderFbList(); $("#fbClearFilter").classList.remove("hidden"); toast("已筛选：" + b.text); }
  });
  fbCanvas.addEventListener("mousemove", (e) => {
    const b = fbCloudHit(e);
    fbCanvas.title = b ? `${b.text}（出现 ${b.count} 次 · ${b.ups} up）` : "";
    fbCanvas.style.cursor = b ? "pointer" : "default";
  });
  initCloudResizer();


  // 思路提炼：绑定
  $("#advisorSendBtn").addEventListener("click", advisorSend);
  $("#advisorInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); advisorSend(); }
  });
  $("#advisorNewBtn").addEventListener("click", advisorNew);
  $$("#advisorStarters .chip").forEach((b) =>
    b.addEventListener("click", () => { $("#advisorInput").value = b.dataset.q; $("#advisorInput").focus(); }));
  $("#advisorGuideBtn").addEventListener("click", generateAdvisorGuide);
  $("#advisorGuideCopy").addEventListener("click", () => copyText(state.advisorGuideMd || "", $("#advisorGuideCopy")));
  $("#advisorGuideDownload").addEventListener("click", () =>
    downloadText(state.advisorGuideMd || "", "提炼指南.md"));

  // 下拉窗口（思路提炼左右两栏 + 检索依据子窗口）：表头点击折叠 / 展开
  document.addEventListener("click", (e) => {
    const head = e.target.closest(".win-head[data-toggle]");
    if (!head) return;
    // 点击窗口表头折叠/展开；忽略面板内交互控件（如输入框、选择器）的冒泡
    if (e.target.closest("button, textarea, select, input")) return;
    const win = document.getElementById(head.dataset.toggle);
    if (!win) return;
    win.classList.toggle("collapsed");
  });

  updateHint();
}

// ---------- 通用弹窗（承载"显式流程"）----------
function openFlowModal(title, el) {
  if (!el) return;
  el._wasHidden = el.classList.contains("hidden");
  el.classList.remove("hidden");
  el._origParent = el.parentNode;
  el._origNext = el.nextSibling;
  $("#modalTitle").textContent = title;
  $("#modalBody").appendChild(el);
  $("#flowModal").classList.remove("hidden");
}
function closeFlowModal() {
  const el = $("#modalBody").firstElementChild;
  if (el) {
    if (el._origParent) el._origParent.insertBefore(el, el._origNext);
    if (el._wasHidden) el.classList.add("hidden");
    // 关闭窗口后，若主内容区未展示则回退到空状态
    if (el.id === "researchSetup" && $("#researchWorkspace").classList.contains("hidden"))
      $("#researchHome").classList.remove("hidden");
    if (el.id === "paperSetup" && $("#paperChat").classList.contains("hidden"))
      $("#paperEmpty").classList.remove("hidden");
  }
  $("#flowModal").classList.add("hidden");
}

function updateHint() {
  const map = { quick: "3 子问题 · ~12 篇候选", standard: "4 子问题 · ~24 篇候选", max: "6 子问题 · ~48 篇候选" };
  let hint = "预计：" + map[$("#depth").value] + " · 分阶段流式返回";
  const cc = parseInt($("#citeCount").value, 10);
  if (cc > 0) hint += ` · 目标引用 ${cc} 篇`;
  $("#depthHint").textContent = hint;
}

// ---------- research intent recognition ----------
const INTENT_LABELS = {
  task_type: { literature_review: "文献综述", tech_survey: "技术调研", proposal: "开题汇报", plan_report: "项目方案" },
  style: { academic: "学术综述", advisor: "导师汇报", technical: "技术方案", concise: "简洁版" },
  depth: { quick: "Quick", standard: "Standard", max: "Max" },
  language: { zh: "中文", en: "English" },
};
async function detectIntent() {
  const q = $("#queryInput").value.trim();
  if (!q) { hideIntentBanner(); return; }
  try {
    const r = await fetch("/api/research/intent", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: q }),
    });
    const d = await r.json();
    if (!d.available || d.confidence < 0.6 || state.intentLocked) return;
    $("#taskType").value = d.task_type;
    $("#style").value = d.style;
    $("#depth").value = d.depth;
    $("#language").value = d.language;
    updateHint();
    showIntentBanner(d);
  } catch {}
}
function showIntentBanner(d) {
  const b = $("#intentBanner");
  const t = `${INTENT_LABELS.task_type[d.task_type] || d.task_type} · ${INTENT_LABELS.style[d.style] || d.style} · ${INTENT_LABELS.depth[d.depth] || d.depth}`;
  b.innerHTML = `🤖 已按输入推荐：<b>${t}</b> <span class="ib-reason">${esc(d.reason || "")}</span> <span class="ib-hint">（已自动套用，可手动调整）</span>`;
  b.classList.remove("hidden");
}
function hideIntentBanner() { $("#intentBanner").classList.add("hidden"); }

// ---------- "猜你想搜" suggestions ----------
async function loadSuggestions() {
  try {
    const r = await fetch("/api/suggestions");
    const d = await r.json();
    const gw = $("#guessWrap");
    gw.innerHTML = (d.suggestions || []).map((s) => {
      const t = typeof s === "string" ? s : (s.topic || "");
      return `<span class="chip ex" data-ex="${esc(t)}" title="${esc(t)}">${esc(trunc(t, 18))}</span>`;
    }).join("");
    bindExChips(gw);
    const rw = $("#recentWrap"), rl = $("#recentList");
    if (d.recent && d.recent.length) {
      rl.innerHTML = d.recent.map((s) =>
        `<span class="chip ex" data-ex="${esc(s)}" title="${esc(s)}">${esc(trunc(s, 18))}</span>`).join("");
      bindExChips(rl);
      rw.classList.remove("hidden");
    } else rw.classList.add("hidden");
  } catch {}
}
function bindExChips(container) {
  container.querySelectorAll(".chip[data-ex]").forEach((b) =>
    b.addEventListener("click", () => {
      $("#queryInput").value = b.dataset.ex;
      state.intentLocked = false; hideIntentBanner(); detectIntent();
    }));
}

// ---------- 深度研究首页：推荐研究 + 最近的研究（填充留白） ----------
function setRecentCount(n) {
  const el = $("#recentCount");
  if (!el) return;
  if (n > 0) { el.textContent = `共 ${n} 项`; el.style.display = ""; }
  else { el.style.display = "none"; }
}
async function loadResearchHome() {
  // 推荐研究：与「猜你想搜」同源（基于用户画像 + 最近研究内容，低延迟缓存）
  try {
    const r = await fetch("/api/suggestions");
    const d = await r.json();
    const items = (d.suggestions || []).slice(0, 6);
    const grid = $("#guessGrid");
    if (!items.length) { grid.innerHTML = `<div class="rr-empty">暂无推荐</div>`; }
    else {
      grid.innerHTML = items.map((s) => {
        const t = typeof s === "string" ? s : (s.topic || "");
        const kws = (typeof s === "string" ? [] : (s.keywords || []));
        return `<button class="rec-card" data-ex="${esc(t)}" title="${esc(t)}">
           <span class="rec-body">
             <span class="rec-title">${esc(t)}</span>
             <span class="rec-tags">${kws.map((k) => `<span class="rec-tag">${esc(k)}</span>`).join("")}</span>
           </span>
         </button>`;
      }).join("");
      grid.querySelectorAll(".rec-card").forEach((b) =>
        b.addEventListener("click", () => {
          $("#queryInput").value = b.dataset.ex;
          state.intentLocked = false; hideIntentBanner(); detectIntent();
          $("#researchEmptyBtn").click();
        }));
    }
  } catch {}
  // 最近的研究
  try {
    const r = await fetch("/api/history");
    const d = await r.json();
    window._history = d.items || [];
    const items = window._history.filter((h) => h.kind === "research").slice(0, 5);
    const box = $("#recentResearch");
    setRecentCount(items.length);
    if (!items.length) { box.innerHTML = `<div class="rr-empty">还没有研究记录，点击上方主题开始第一项研究吧。</div>`; return; }
    box.innerHTML = items.map((h) =>
      `<div class="rec-card" data-ts="${esc(h.ts)}">
         <span class="rec-body">
           <span class="rec-title">${esc(h.title)}</span>
           <span class="rec-meta">${esc(h.sub || "")} · ${fmtTs(h.ts)}</span>
         </span>
       </div>`).join("");
    box.querySelectorAll(".rec-card").forEach((el) =>
      el.addEventListener("click", () => {
        const idx = window._history.findIndex((x) => x.ts === el.dataset.ts);
        if (idx >= 0) openHistory(idx);
      }));
  } catch {}
}

// ---------- 各页面的使用指南内容 ----------
const GUIDE = {
  research: { name: "深度研究", steps: [
    { t: "输入主题", d: "点击「＋ 新建研究」，填写你想深挖的课题，也可上传资料作为上下文。" },
    { t: "设定配置", d: "选择任务类型、写作风格、语言与深度；「引用文献数量」可控制报告引用的文献篇数（0 表示自动）。" },
    { t: "生成与引用", d: "系统按「规划 → 检索 → 压缩 → 报告 → 引用对齐」分阶段流式返回；完成后可在右侧核对每条引用来源，并在「历史动态」中复盘。" },
  ] },
  search: { name: "文献检索", steps: [
    { t: "选择检索模式", d: "「普通检索」适合翻页浏览、存入文库；「智能检索」会先按你的目的规划检索与分析，再生成带引用的结构化报告。" },
    { t: "普通检索", d: "输入关键词，用「⚙ 筛选」限定年份 / 开放获取 / 类型 / 排序；结果可翻页、批量存入文库或用选中项做研究。" },
    { t: "智能检索", d: "用一句话描述需求（如「近 3-5 年 LLM Agent 在自动文献综述中应用，20 篇，15 中 5 英」），系统提炼目的 → 规划 → 多源检索 → 生成溯源报告，可下载 HTML。" },
  ] },
  paper: { name: "论文研讨", steps: [
    { t: "上传论文", d: "支持 .pdf / .txt / .md，解析在本地服务端完成，全文用于本次研讨。" },
    { t: "围绕全文提问", d: "用三句话概括、追问核心方法、梳理论文局限与可拓展方向，或就具体章节 / 图示提问。" },
    { t: "多轮追问与复用", d: "可换一篇、复制结论；研讨内容可在「历史动态」中查看。" },
  ] },
  studio: { name: "写作助手", steps: [
    { t: "选择工具", d: "摘要生成 / 提纲生成 / 单段综述，轻量快速。" },
    { t: "填写信息", d: "按所选工具的要求填入内容（如摘要需全文、综述需文献要点），再点「生成」。" },
    { t: "生成与复制", d: "一键生成结果，点击「复制」即可粘贴到你的文档。" },
  ] },
  forge: { name: "创造工坊", steps: [
    { t: "发现与收藏", d: "搜索或浏览功能，点击 ★ 收藏常用功能，置于右侧「已收藏」。" },
    { t: "打开功能", d: "点开任意功能即进入一个完全独立的界面，互不干扰。" },
    { t: "新建功能", d: "支持三档设计：一句话（自动生成）、初步设计（对话 + 拖拽）、高级设计（代码模板）。" },
  ] },
  feedback: { name: "反馈看板", steps: [
    { t: "浏览词云", d: "上方问题词云汇聚所有反馈的高频关键词，悬停看次数、点击筛选下方列表。" },
    { t: "查看反馈", d: "点词云或关键词可筛选；上方可按「up 最多 / 最新反馈」排序，并为认同的反馈 up。" },
    { t: "提交建议", d: "选择反馈方面并填写内容后提交；敏感词会自动屏蔽后展示。" },
  ] },
  library: { name: "我的文库", steps: [
    { t: "收集资料", d: "在「文献检索」中保存论文，或在此「上传文档」，构建可靠的研究上下文。" },
    { t: "筛选与排序", d: "按类型 / 关键词搜索，按最近、标题或年份排序。" },
    { t: "用于研究", d: "勾选文献后「用选中项做研究」，作为深度研究的上下文。" },
  ] },
  history: { name: "历史动态", steps: [
    { t: "按模块筛选", d: "切换 全部 / 深度研究 / 文献检索 / 论文研讨 / 写作工坊。" },
    { t: "继续与复盘", d: "点击任意记录继续未完成的任务，或复盘已完成的研究、检索与研讨。" },
    { t: "选择删除", d: "点击右上角「选择删除」进入多选，勾选后可批量删除历史记录。" },
  ] },
  profile: { name: "个人主页", steps: [
    { t: "完善档案", d: "设置头像、昵称、身份、机构与研究领域，建立你的研究者画像。" },
    { t: "添加研究兴趣", d: "输入你关注的方向与关键词，它们会用于「推荐研究」与「猜你想搜」的个性化推荐。" },
    { t: "保存生效", d: "点击「保存个人主页」后，推荐会立即结合你的兴趣更新。" },
  ] },
  settings: { name: "设置", steps: [
    { t: "查看连接", d: "在此查看模型连接状态、接口地址与检索源可用性。" },
    { t: "研究默认偏好", d: "设置默认深度、风格、语言、任务类型与引用文献数量，新建研究会自动套用。" },
    { t: "界面与检索源", d: "调整「最近动态」显示条数，并启用或关闭各检索源。" },
  ] },
};
function openGuide() {
  const g = GUIDE[currentView] || GUIDE.research;
  $("#guideTitle").textContent = `📖 ${g.name} · 使用指南`;
  $("#guideSteps").innerHTML = g.steps.map((s, i) =>
    `<div class="g-step"><span class="g-num">${i + 1}</span><div class="g-text"><b>${s.t}</b><p>${s.d}</p></div></div>`
  ).join("");
  $("#guideModal").classList.remove("hidden");
}

// ---------- 使用指南按钮（单例，注入当前页头部，随页面滚动，不再固定悬浮遮挡） ----------
let guideBtnEl = null;
function ensureGuideBtn() {
  if (!guideBtnEl) {
    guideBtnEl = document.createElement("button");
    guideBtnEl.id = "guideBtn";
    guideBtnEl.className = "btn-ghost guide-btn";
    guideBtnEl.textContent = "📖 使用指南";
    guideBtnEl.title = "使用指南";
    guideBtnEl.addEventListener("click", openGuide);
  }
  return guideBtnEl;
}
function placeGuideInHead(name) {
  const head = document.querySelector("#view-" + name + " .page-head");
  if (head) head.appendChild(ensureGuideBtn());
}

// ---------- view switching ----------
let currentView = "research";
function switchView(name) {
  currentView = name;
  placeGuideInHead(name);
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$(".view").forEach((v) => v.classList.add("hidden"));
  $("#view-" + name).classList.remove("hidden");
  if (name === "library") renderLibrary();
  if (name === "history") renderHistory();
  if (name === "settings") renderSettings();
  if (name === "profile") renderProfile();
  if (name === "research") { loadSuggestions(); loadResearchHome(); }
  if (name === "forge") { renderFeatCats(); loadFeatures(); }
  if (name === "feedback") loadFeedback();
  renderRightRail();
  renderRightCitations();  // 切换页面时，「本次引用」同步为该页面对应的引用结果
}

// ---------- upload ----------
async function handleUpload(e) {
  for (const f of [...e.target.files]) {
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      if (!r.ok) throw new Error((await r.json()).detail || "上传失败");
      const d = await r.json();
      state.uploads.push(d);
      renderUploads();
      toast(`已解析 ${d.filename}（${d.chars} 字）`);
    } catch (err) { toast(err.message, true); }
  }
}
function renderUploads() {
  $("#uploadList").innerHTML = state.uploads
    .map((u) => `<span class="upload-item">📄 ${u.filename}</span>`).join("");
}

function showPending() {
  const box = $("#pendingBox");
  if (!state.pendingSources.length) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  box.innerHTML = `已带入 <b>${state.pendingSources.length}</b> 篇资料作为研究上下文
    <span class="clear-pending" id="clearPending">清除</span>`;
  $("#clearPending").onclick = () => { state.pendingSources = []; showPending(); };
}

// ---------- research stream ----------
async function startResearch() {
  const query = $("#queryInput").value.trim();
  if (!query && !state.pendingSources.length) return toast("请输入研究主题", true);
  const payload = {
    query: query || state.pendingSources.map((s) => s.title).join("；").slice(0, 200),
    task_type: $("#taskType").value,
    language: $("#language").value,
    style: $("#style").value,
    depth: $("#depth").value,
    sources: ["paper"],
    focus: $("#focus").value.trim() || null,
    citation_count: (parseInt($("#citeCount").value, 10) || 0) || null,
    upload_ids: state.uploads.map((u) => u.upload_id),
    extra_sources: state.pendingSources,
  };

  Object.assign(state, { sources: {}, packets: [], sections: {} });
  closeFlowModal();
  $("#researchSetup").classList.add("hidden");
  $("#researchWorkspace").classList.remove("hidden");
  $("#researchHome").classList.add("hidden");
  resetWorkspace();
  $("#startBtn").disabled = true;
  try {
    const resp = await fetch("/api/research/stream", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error("请求失败：" + resp.status);
    await consumeSSE(resp.body, handleEvent);
  } catch (err) { toast(err.message, true); log("错误：" + err.message); }
  finally { $("#startBtn").disabled = false; state.pendingSources = []; showPending(); }
}

function resetWorkspace() {
  $("#report").innerHTML = ""; $("#log").innerHTML = ""; $("#evidenceBoard").innerHTML = "";
  $("#hypoBoard").innerHTML = ""; $("#graphBoard").innerHTML = ""; $("#gapBoard").innerHTML = ""; $("#expBoard").innerHTML = "";
  $("#citationList").innerHTML = ""; $("#subqList").innerHTML = ""; $("#outlineList").innerHTML = "";
  renderRightCitations();  // 新研究开始，清空右侧「本次引用」
  $("#goalCard").textContent = "生成研究计划中…"; $("#goalCard").className = "card muted";
  $$(".metric .m-val").forEach((m) => (m.textContent = m.id === "mSources" || m.id === "mPackets" || m.id === "mTokens" ? "0" : "–"));
  $$(".stage").forEach((s) => s.classList.remove("active", "completed"));
}

async function consumeSSE(stream, onEvent) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const chunks = buf.split("\n\n");
    buf = chunks.pop();
    for (const chunk of chunks) {
      let event = "message", data = "";
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) { try { onEvent(event, JSON.parse(data)); } catch {} }
    }
  }
}

function handleEvent(event, data) {
  switch (event) {
    case "task_created": state.taskId = data.task_id; break;
    case "status": setStage(data.stage); log("▶ " + data.label); break;
    case "plan": renderPlan(data.plan); setMetric("mTtfp", data.ttfp); log("✓ 研究计划已生成"); break;
    case "search_progress": log(`🔍 「${trunc(data.question, 18)}」检索到 ${data.count} 条`); break;
    case "evidence_sources": renderSources(data.sources); setMetric("mTtfe", data.ttfe);
      setMetric("mSources", data.sources.length); log(`✓ 共 ${data.sources.length} 个来源`); break;
    case "compress_progress": setMetric("mPackets", data.packets); break;
    case "evidence_packets": renderPackets(data.packets); setMetric("mRatio", data.compression_ratio + "x");
      log(`✓ 压缩为 ${data.packets.length} 个证据包（压缩比 ${data.compression_ratio}x）`); break;
    case "hypotheses": renderHypotheses(data.items); log(`✓ 生成 ${data.items.length} 条研究假设`); break;
    case "evidence_graph": renderGraph(data.edges); log(`✓ 构建证据图谱（${data.edges.length} 条关系）`); break;
    case "gaps": renderGaps(data.items); log(`✓ 识别 ${data.items.length} 处研究空白`); break;
    case "experiments": renderExperiments(data.items); log(`✓ 设计 ${data.items.length} 个验证实验`); break;
    case "section_start": startSection(data.section_id, data.title); break;
    case "section_delta": appendDelta(data.section_id, data.delta); break;
    case "section_done": finishSection(data); setMetric("mTtfr", data.ttfr); break;
    case "done": completeAll(data.metrics); break;
    case "error": toast(data.message, true); log("✗ " + data.message); break;
  }
}

function setStage(stage) {
  const order = ["planning", "searching", "compressing", "hypothesizing", "graphing", "gapping", "experimenting", "writing", "done"];
  const idx = order.indexOf(stage);
  $$(".stage").forEach((el) => {
    const i = order.indexOf(el.dataset.stage);
    el.classList.toggle("active", i === idx);
    el.classList.toggle("completed", i < idx);
  });
}
function renderPlan(plan) {
  $("#goalCard").textContent = plan.rewritten_goal;
  $("#goalCard").className = "card";
  $("#subqList").innerHTML = plan.subquestions.map((sq) => `
    <div class="subq"><div class="q">${esc(sq.question)}</div>
      ${sq.rationale ? `<div class="r">${esc(sq.rationale)}</div>` : ""}
      <div class="qs">${(sq.queries || []).map((q) => `<span>${esc(q)}</span>`).join("")}</div></div>`).join("");
  $("#outlineList").innerHTML = plan.report_outline.map((o) => `<li>${esc(o)}</li>`).join("");
}
function renderSources(sources) {
  sources.forEach((s) => (state.sources[s.source_id] = s));
  $("#citationList").innerHTML = sources.map((s) => `
    <div class="src-card" id="src-${s.source_id}">
      <span class="src-id">[${s.source_id}] · ${typeLabel(s.source_type)}</span>
      <div class="src-title">${s.url ? `<a href="${s.url}" target="_blank">${esc(s.title)}</a>` : esc(s.title)}</div>
      <div class="src-meta">${esc((s.authors || []).slice(0,3).join(", "))}${s.year ? " · " + s.year : ""}${s.venue ? " · " + esc(s.venue) : ""}</div>
      <div class="src-abs">${esc(s.abstract || "")}</div>
    </div>`).join("");
  renderRightCitations();
}
function renderPackets(packets) {
  state.packets = packets;
  $("#evidenceBoard").innerHTML = packets.map((p) => `
    <div class="ev-card"><div class="ev-topic">${esc(p.topic || "证据包")}</div>
      ${p.claim ? `<div class="ev-row"><b>结论：</b>${esc(p.claim)}</div>` : ""}
      ${p.method ? `<div class="ev-row"><b>方法：</b>${esc(p.method)}</div>` : ""}
      ${p.limitation ? `<div class="ev-row"><b>局限：</b>${esc(p.limitation)}</div>` : ""}
      <div class="ev-refs">${(p.support_source_ids || []).map(citeChip).join("")}
        <span style="font-size:11px;color:var(--muted)">支撑度 ${(p.support_score||0).toFixed(2)}</span></div>
    </div>`).join("");
}
function renderHypotheses(items) {
  const box = $("#hypoBoard");
  if (!items || !items.length) { box.innerHTML = `<div class="empty">未生成研究假设。</div>`; return; }
  box.innerHTML = items.map((h) => `
    <div class="ins-card">
      <div class="ins-head"><span class="ins-tag">${esc(h.hypothesis_id)}</span>
        <span class="ins-conf">置信 ${(h.confidence||0).toFixed(2)}</span></div>
      <div class="ins-title">${esc(h.statement)}</div>
      ${h.rationale ? `<div class="ins-row"><b>依据：</b>${esc(h.rationale)}</div>` : ""}
      ${h.testability ? `<div class="ins-row"><b>可验证：</b>${esc(h.testability)}</div>` : ""}
      ${(h.based_on||[]).length ? `<div class="ins-refs">${(h.based_on).map((b)=>`<span class="ref-chip">${esc(b)}</span>`).join("")}</div>` : ""}
    </div>`).join("");
}
function renderGaps(items) {
  const box = $("#gapBoard");
  if (!items || !items.length) { box.innerHTML = `<div class="empty">未识别到研究空白。</div>`; return; }
  box.innerHTML = items.map((g) => `
    <div class="ins-card">
      <div class="ins-head"><span class="ins-tag gap">${esc(g.gap_id)}</span></div>
      <div class="ins-title">${esc(g.title)}</div>
      ${g.description ? `<div class="ins-row">${esc(g.description)}</div>` : ""}
      ${g.why ? `<div class="ins-row"><b>为何是空白：</b>${esc(g.why)}</div>` : ""}
      ${g.suggested_direction ? `<div class="ins-row"><b>建议方向：</b>${esc(g.suggested_direction)}</div>` : ""}
      ${(g.related_hypotheses||[]).length ? `<div class="ins-refs">关联：${(g.related_hypotheses).map((x)=>`<span class="ref-chip">${esc(x)}</span>`).join("")}</div>` : ""}
    </div>`).join("");
}
function renderExperiments(items) {
  const box = $("#expBoard");
  if (!items || !items.length) { box.innerHTML = `<div class="empty">未设计验证实验。</div>`; return; }
  box.innerHTML = items.map((x) => `
    <div class="ins-card">
      <div class="ins-head"><span class="ins-tag exp">${esc(x.experiment_id)}</span>
        ${x.hypothesis_ref ? `<span class="ins-ref">针对 ${esc(x.hypothesis_ref)}</span>` : ""}</div>
      <div class="ins-title">${esc(x.title)}</div>
      ${x.method ? `<div class="ins-row"><b>方法：</b>${esc(x.method)}</div>` : ""}
      ${x.dataset ? `<div class="ins-row"><b>数据：</b>${esc(x.dataset)}</div>` : ""}
      ${(x.metrics||[]).length ? `<div class="ins-refs">指标：${(x.metrics).map((m)=>`<span class="ref-chip">${esc(m)}</span>`).join("")}</div>` : ""}
      ${x.baseline ? `<div class="ins-row"><b>基线：</b>${esc(x.baseline)}</div>` : ""}
      ${x.expected_outcome ? `<div class="ins-row"><b>预期：</b>${esc(x.expected_outcome)}</div>` : ""}
    </div>`).join("");
}
function renderGraph(edges) {
  const box = $("#graphBoard");
  const pkts = state.packets || [];
  if (!pkts.length || !edges || !edges.length) {
    box.innerHTML = `<div class="empty">证据不足，无法构建图谱。</div>`; return;
  }
  const labelOf = {}; pkts.forEach((p) => (labelOf[p.packet_id] = (p.topic || p.packet_id)));
  const ids = pkts.map((p) => p.packet_id);
  const n = ids.length, cx = 320, cy = 200, rx = 250, ry = 150;
  const pos = {};
  ids.forEach((id, i) => {
    const a = (i / Math.max(1, n)) * Math.PI * 2 - Math.PI / 2;
    pos[id] = { x: cx + rx * Math.cos(a), y: cy + ry * Math.sin(a) };
  });
  const color = { support: "#7ee0c0", contradict: "#f78fb3", extend: "#6ea8fe", specialize: "#e0a3ff" };
  const nodesSvg = ids.map((id) => {
    const p = pos[id];
    return `<g><circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="20" fill="#1b2433" stroke="#3a4761"/>
      <text x="${p.x.toFixed(1)}" y="${(p.y-26).toFixed(1)}" fill="#cdd6e6" font-size="11" text-anchor="middle">${esc(id)}</text>
      <text x="${p.x.toFixed(1)}" y="${(p.y+4).toFixed(1)}" fill="#9fb0cc" font-size="10" text-anchor="middle">${esc(trunc(labelOf[id]||id,8))}</text></g>`;
  }).join("");
  const edgesSvg = edges.map((e) => {
    const a = pos[e.from_packet], b = pos[e.to_packet]; if (!a || !b) return "";
    const c = color[e.relation] || "#9fb0cc";
    return `<line x1="${a.x.toFixed(1)}" y1="${a.y.toFixed(1)}" x2="${b.x.toFixed(1)}" y2="${b.y.toFixed(1)}" stroke="${c}" stroke-width="1.6" marker-end="url(#ar-${e.relation})" opacity="0.85"/>`;
  }).join("");
  const legend = Object.entries({ support: "相互支持", contradict: "相互矛盾", extend: "递进/延伸", specialize: "特例" })
    .map(([k, t]) => `<span class="gg-leg"><i style="background:${color[k]}"></i>${t}</span>`).join("");
  const list = edges.map((e) => `<li><span class="gg-rel" style="color:${color[e.relation]||'#9fb0cc'}">${relLabel(e.relation)}</span>
    <b>${esc(e.from_packet)}</b> → <b>${esc(e.to_packet)}</b> ${esc(e.note||"")}</li>`).join("");
  box.innerHTML = `
    <svg viewBox="0 0 640 400" class="gg-svg" preserveAspectRatio="xMidYMid meet">
      <defs>${Object.keys(color).map((k)=>`<marker id="ar-${k}" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="${color[k]}"/></marker>`).join("")}</defs>
      ${edgesSvg}${nodesSvg}
    </svg>
    <div class="gg-legend">${legend}</div>
    <ul class="gg-list">${list}</ul>`;
}
function relLabel(r) {
  return ({ support: "支持", contradict: "矛盾", extend: "延伸", specialize: "特例" })[r] || r;
}
function startSection(id, title) {
  state.sections[id] = { title, content: "" };
  const num = Object.keys(state.sections).length;
  const el = document.createElement("div");
  el.className = "report-section"; el.id = "sec-" + id;
  el.innerHTML = `<h2><span class="num">${num}</span>${esc(title)}</h2><div class="report-body" id="body-${id}"></div>`;
  $("#report").appendChild(el);
}
function appendDelta(id, delta) {
  const s = state.sections[id]; if (!s) return;
  s.content += delta;
  $("#body-" + id).innerHTML = renderMarkdown(s.content);
}
function finishSection(data) {
  const s = state.sections[data.section_id]; if (!s) return;
  s.content = data.content;
  $("#body-" + data.section_id).innerHTML = renderMarkdown(data.content);
  const bar = document.createElement("div");
  bar.className = "sec-toolbar";
  const actions = [["expand","扩写"],["shorten","精简"],["add_citation","补引用"],["rebuttal","反方观点"],["restyle","改风格"]];
  bar.innerHTML = actions.map(([a,l]) => `<button class="sec-btn" data-a="${a}" data-s="${data.section_id}">${l}</button>`).join("");
  $("#sec-" + data.section_id).appendChild(bar);
  bar.querySelectorAll(".sec-btn").forEach((b) =>
    b.addEventListener("click", () => refineSection(b.dataset.s, b.dataset.a)));
  log(`✓ 「${trunc(data.title,14)}」完成，引用 ${data.citations.length} 处`);
}
async function refineSection(sectionId, action) {
  toast("正在重写本节…");
  try {
    const body = { task_id: state.taskId, section_id: sectionId, action };
    if (action === "restyle") body.style = $("#style").value;
    const r = await fetch("/api/refine", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error((await r.json()).detail || "重写失败");
    const d = await r.json();
    state.sections[sectionId].content = d.content;
    $("#body-" + sectionId).innerHTML = renderMarkdown(d.content);
    toast("本节已更新");
  } catch (err) { toast(err.message, true); }
}
function completeAll(metrics) {
  setStage("done");
  $$(".stage").forEach((el) => el.classList.add("completed"));
  if (metrics.tokens) setMetric("mTokens", metrics.tokens.total_tokens);
  if (metrics.num_citations != null) setMetric("mCites", metrics.num_citations);
  loadResearchHome();
  log(`🎉 研究完成：${metrics.num_sections} 章 · ${metrics.total_tokens || metrics.tokens?.total_tokens || 0} tokens`);
  toast("研究报告已生成完成");
  renderHistory();
  renderRightRail();
  loadSuggestions();
}

// reload a stored task into the workspace (history view)
function loadTaskIntoWorkspace(t) {
  Object.assign(state, { sources: {}, packets: [], sections: {} });
  state.taskId = t.task_id;
  $("#researchSetup").classList.add("hidden");
  $("#researchHome").classList.add("hidden");
  $("#researchWorkspace").classList.remove("hidden");
  resetWorkspace();
  if (t.plan) renderPlan(t.plan);
  if (t.sources) renderSources(t.sources);
  if (t.packets) renderPackets(t.packets);
  (t.sections || []).forEach((sec) => showStoredSection(sec));
  if (t.metrics?.timings) {
    setMetric("mTtfp", t.metrics.timings.ttfp);
    setMetric("mTtfe", t.metrics.timings.ttfe);
    setMetric("mTtfr", t.metrics.timings.ttfr);
    setMetric("mTtr", t.metrics.timings.ttr);
  }
  if (t.metrics?.compression) setMetric("mRatio", t.metrics.compression.compression_ratio + "x");
  setMetric("mSources", t.sources?.length || 0);
  setMetric("mPackets", t.packets?.length || 0);
  setMetric("mTokens", t.metrics?.tokens?.total_tokens || 0);
  $$(".stage").forEach((el) => { el.classList.remove("active"); el.classList.add("completed"); });
  log(`已载入历史任务：${t.request.query}`);
}
function showStoredSection(sec) {
  state.sections[sec.section_id] = { title: sec.section_title, content: sec.content };
  const num = Object.keys(state.sections).length;
  const el = document.createElement("div");
  el.className = "report-section"; el.id = "sec-" + sec.section_id;
  el.innerHTML = `<h2><span class="num">${num}</span>${esc(sec.section_title)}</h2><div class="report-body" id="body-${sec.section_id}"></div>`;
  $("#report").appendChild(el);
  $("#body-" + sec.section_id).innerHTML = renderMarkdown(sec.content);
  const bar = document.createElement("div");
  bar.className = "sec-toolbar";
  const actions = [["expand","扩写"],["shorten","精简"],["add_citation","补引用"],["rebuttal","反方观点"],["restyle","改风格"]];
  bar.innerHTML = actions.map(([a,l]) => `<button class="sec-btn" data-a="${a}" data-s="${sec.section_id}">${l}</button>`).join("");
  el.appendChild(bar);
  bar.querySelectorAll(".sec-btn").forEach((b) =>
    b.addEventListener("click", () => refineSection(b.dataset.s, b.dataset.a)));
}

// ---------- literature search ----------
function switchSearchMode(mode) {
  state.searchMode = mode;
  $$(".mode-btn").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  const smart = mode === "smart";
  $("#smartPanel").classList.toggle("hidden", !smart);
  $("#normalPanel").classList.toggle("hidden", smart);
  const hasResults = !!(state.litResults && state.litResults.length);
  $("#recoPanel").classList.toggle("hidden", smart || hasResults);
  $("#smartHint").classList.toggle("hidden", !smart);
  $("#litQuery").placeholder = smart
    ? "输入研究方向，例如：扩散模型在视频生成中的应用"
    : "检索主题 / 关键词 / 论文标题（可在「⚙ 筛选」中限定年份与排序）";
  $("#litSearchBtn").textContent = smart ? "生成检索报告" : "检索";
  if (!smart) loadRecommendations();
}

function _yearParam() {
  const manual = $("#litYearManual").value.trim();
  if (manual) return new Date().getFullYear() - parseInt(manual, 10);
  const yearSel = $("#litYear").value;
  if (!yearSel) return "";
  return new Date().getFullYear() - parseInt(yearSel, 10);
}

function runSearch() {
  if (state.searchMode === "smart") return smartSearch();
  return doSearch();
}

// -- 普通检索（流式 + 翻页）--
async function doSearch() {
  const q = $("#litQuery").value.trim();
  if (!q) return toast("请输入检索关键词", true);
  state.litQuery = q;
  state.litPage = 1;
  state.litResults = [];
  $("#recoPanel").classList.add("hidden");
  $("#litResults").innerHTML = `<div class="empty">检索中…</div>`;
  $("#litMeta").textContent = "";
  $("#loadMoreWrap").classList.add("hidden");
  await fetchSearchPage(true);
}

async function loadMore() {
  state.litPage += 1;
  $("#loadMoreBtn").textContent = "加载中…";
  await fetchSearchPage(false);
  $("#loadMoreBtn").textContent = "加载更多结果";
}

async function fetchSearchPage(reset) {
  const sources = $("#litSources").value;
  const yearParam = _yearParam();
  const oa = $("#litOa").value;
  const docType = $("#litType").value;
  let base = `/api/search/stream?q=${encodeURIComponent(state.litQuery)}&sources=${sources}&limit=15&page=${state.litPage}`;
  if (yearParam) base += `&year=${yearParam}`;
  if (oa) base += `&oa=${oa}`;
  if (docType) base += `&type=${encodeURIComponent(docType)}`;
  if (reset) state.litResults = [];
  let pageCount = 0;
  try {
    const resp = await fetch(base);
    if (!resp.ok) throw new Error("请求失败：" + resp.status);
    await consumeSSE(resp.body, (ev, data) => {
      if (ev === "source_batch") {
        pageCount += data.count;
        state.litResults.push(...data.items);
        renderLitResults(state.litResults);
        $("#litMeta").textContent = `共 ${state.litResults.length} 条结果 · 第 ${state.litPage} 页 · 正在检索 ${data.source}…`;
      } else if (ev === "done") {
        $("#litMeta").textContent = `共 ${state.litResults.length} 条结果（第 ${state.litPage} 页，${sources.replace(/,/g," / ")}）`;
        $("#loadMoreWrap").classList.toggle("hidden", pageCount === 0);
      } else if (ev === "error") { toast(data.message, true); }
    });
  } catch (e) {
    toast("检索失败：" + e.message, true);
    if (!state.litResults.length) $("#litResults").innerHTML = `<div class="empty">检索失败</div>`;
  }
}

function renderLitResults(results) {
  let arr = results;
  if ($("#litSort").value === "year") arr = results.slice().sort((a, b) => (b.year || 0) - (a.year || 0));
  window._litResults = arr;
  const box = $("#litResults");
  if (!arr.length) { box.innerHTML = `<div class="empty">未找到相关文献，换个关键词试试。</div>`; return; }
  box.innerHTML = arr.map((s, i) => litCardHTML(s, i)).join("");
  box.querySelectorAll(".lit-chk").forEach((c) => c.addEventListener("change", updateSelCount));
  box.querySelectorAll(".lit-save").forEach((b, i) =>
    b.addEventListener("click", () => saveOneToLibrary(arr[i])));
}
function applyLitSort() { if (state.litResults.length) renderLitResults(state.litResults); }
function litCardHTML(s, i) {
  return `
    <div class="lit-card" data-i="${i}">
      <div class="lit-top">
        <input type="checkbox" class="lit-chk" />
        <div>
          <div class="lit-title">${s.url ? `<a href="${esc(s.url)}" target="_blank">${esc(s.title)}</a>` : esc(s.title)}
            <span class="lit-tag">${esc(s.retrieved_from || "")}</span>
            ${s.year ? `<span class="lit-year">${esc(s.year)}</span>` : ""}</div>
          <div class="lit-meta">${esc((s.authors||[]).slice(0,4).join(", "))}${s.venue ? " · " + esc(s.venue) : ""}</div>
        </div>
      </div>
      <div class="lit-abs">${esc((s.abstract || s.snippet || "").slice(0, 320))}</div>
      <div class="lit-foot">
        <button class="btn-soft lit-save">存入文库</button>
      </div>
    </div>`;
}

// -- 智能检索（多步检索 + 简要报告，流式）--
async function smartSearch() {
  const topic = $("#litQuery").value.trim();
  if (!topic) return toast("请输入研究方向", true);
  const steps = $("#smartSteps"), report = $("#smartReport"), srcBox = $("#smartSources");
  steps.innerHTML = ""; srcBox.innerHTML = ""; $("#smartSrcHead").classList.add("hidden");
  $("#recoPanel").classList.add("hidden");
  report.innerHTML = `<div class="empty">正在拆解检索意图…</div>`;
  $("#smartActions").classList.add("hidden");
  $("#litSearchBtn").disabled = true;
  window._smartSources = [];
  window._smartCited = [];
  renderRightCitations();
  let reportMd = "";
  state.smartReportMd = "";
  try {
    const resp = await fetch("/api/search/smart/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, language: $("#language").value, steps: 3, per_query: 6 }),
    });
    if (!resp.ok) throw new Error("请求失败：" + resp.status);
    await consumeSSE(resp.body, (ev, data) => {
      if (ev === "status") smartStep(`▶ ${data.label}`);
      else if (ev === "queries") {
        smartStep(`🎯 提炼目的：${data.intent}`);
        data.queries.forEach((q, i) => smartStep(`🔎 检索式 ${i+1}：${q}`));
      }
      else if (ev === "format_plan") {
        const groups = (data.groups || []).join(" → ");
        let plan = `📐 已按你的目的规划：${data.title || ""}`;
        if (groups) plan += `（检索分层：${groups}）`;
        if (data.count_hint) plan += ` · ${data.count_hint}`;
        smartStep(plan);
        (data.analysis_sections || []).forEach((s, i) =>
          smartStep(`   └ 分析节 ${i + 1}：${s.heading} —— ${s.focus || ""}`));
        if (data.format) smartStep(`   └ 生成格式：${data.format}`);
      }
      else if (ev === "step_done") smartStep(`✓ 「${trunc(data.query, 26)}」新增 ${data.found} 篇`);
      else if (ev === "sources") { window._smartSources = data.sources; window._smartCited = data.sources; renderSmartSources(data.sources); renderRightCitations(); }
      else if (ev === "report_delta") { reportMd += data.delta; state.smartReportMd = reportMd; report.innerHTML = renderMarkdown(reportMd); }
      else if (ev === "done") {
        smartStep(`🎉 检索报告完成，共 ${data.count} 篇文献`);
        $("#smartActions").classList.remove("hidden");
        if (!reportMd.trim()) {
          report.innerHTML = `<div class="empty">本次未生成文字报告（可能是模型未返回内容）。已检索到 ${data.count} 篇文献，可在下方「检索到的文献」中查看并一键溯源。</div>`;
        }
        renderRightCite(reportMd);
      }
      else if (ev === "error") { toast(data.message, true); smartStep("✗ " + data.message); }
    });
  } catch (e) { toast(e.message, true); report.innerHTML = `<div class="empty">生成失败：${esc(e.message)}</div>`; }
  finally { $("#litSearchBtn").disabled = false; }
}
function smartStep(msg) {
  const d = document.createElement("div");
  d.className = "smart-step"; d.textContent = msg;
  const box = $("#smartSteps");
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;  // 固定高度内自动滚到最新
}
function renderSmartSources(sources) {
  $("#smartSrcHead").classList.remove("hidden");
  const box = $("#smartSources");
  box.innerHTML = sources.map((s) => `
    <div class="lit-card" id="src-${s.source_id}">
      <div class="lit-title"><span class="src-id">[${s.source_id}]</span>
        ${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>` : esc(s.title)}</div>
      <div class="lit-meta">${esc((s.authors||[]).slice(0,4).join(", "))}${s.year ? " · " + s.year : ""}${s.venue ? " · " + esc(s.venue) : ""}</div>
      <div class="lit-abs">${esc((s.abstract || s.snippet || "").slice(0, 240))}</div>
      <div class="lit-foot">
        <button class="btn-soft" onclick='saveSmartSource("${s.source_id}")'>存入文库</button>
        <button class="btn-soft" onclick='showCitePop("${s.source_id}")'>🔗 溯源</button>
      </div>
    </div>`).join("");
}
window.saveSmartSource = async (sid) => {
  const s = (window._smartSources || []).find((x) => x.source_id === sid);
  if (s) await saveOneToLibrary(s);
};

// ---------- 检索筛选弹层（集成：年份 / 手动近N年 / 排序）----------
function updateFilterChips() {
  const manual = $("#litYearManual").value.trim();
  const yearSel = $("#litYear").value;
  const sort = $("#litSort").value;
  const oa = $("#litOa").value;
  const docType = $("#litType").value;
  const parts = [];
  if (manual) parts.push(`近 ${manual} 年`);
  else if (yearSel) parts.push(`近 ${yearSel} 年`);
  else parts.push("不限年份");
  if (oa) parts.push("仅开放获取");
  if (docType === "article") parts.push("期刊论文");
  else if (docType === "preprint") parts.push("预印本");
  else if (docType === "book") parts.push("图书");
  parts.push(sort === "year" ? "按年份排序" : "按相关度排序");
  $("#litFilterChips").innerHTML = parts.map((p) => `<span class="filt-chip">${esc(p)}</span>`).join("");
}
function bindFilterPopover() {
  const pop = $("#litFilterPop");
  $("#litFilterBtn").addEventListener("click", (e) => {
    e.stopPropagation();
    updateFilterChips();
    pop.classList.toggle("hidden");
  });
  // 下拉与手动输入互斥
  $("#litYear").addEventListener("change", () => { if ($("#litYear").value) $("#litYearManual").value = ""; });
  $("#litYearManual").addEventListener("input", () => { if ($("#litYearManual").value.trim()) $("#litYear").value = ""; });
  // 筛选控件变化时，实时同步搜索框下方的筛选关键词
  ["litYear", "litOa", "litType", "litSort"].forEach((id) =>
    document.getElementById(id).addEventListener("change", updateFilterChips));
  $("#litYearManual").addEventListener("input", updateFilterChips);
  $("#filtApply").addEventListener("click", () => {
    pop.classList.add("hidden");
    updateFilterChips();
    if (state.litQuery) doSearch();
  });
  $("#filtReset").addEventListener("click", () => {
    $("#litYear").value = ""; $("#litYearManual").value = ""; $("#litSort").value = "rel";
    $("#litOa").value = ""; $("#litType").value = "";
    updateFilterChips();
    if (state.litQuery) doSearch();
  });
  document.addEventListener("click", (e) => {
    if (!pop.classList.contains("hidden") && !pop.contains(e.target) && e.target.id !== "litFilterBtn")
      pop.classList.add("hidden");
  });
}

// ---------- 首页推荐（填补留白，卡片支持溯源）----------
let _recoLoaded = false;
async function loadRecommendations() {
  if (_recoLoaded) return;
  _recoLoaded = true;
  try {
    const r = await fetch("/api/recommend?limit=6");
    const data = await r.json();
    renderReco(data.results || []);
  } catch (e) {
    $("#recoList").innerHTML = `<div class="empty">推荐加载失败，请检查网络后重试。</div>`;
  }
}
function recoEmoji(src) {
  return { openalex: "📘", crossref: "📗", arxiv: "📙" }[src] || "📄";
}
function renderReco(list) {
  const box = $("#recoList");
  if (!list.length) { box.innerHTML = `<div class="empty">暂无推荐，稍后再来看看～</div>`; return; }
  box.innerHTML = list.map((s) => `
    <div class="reco-card">
      <div class="reco-top">
        <div class="reco-emoji">${recoEmoji(s.retrieved_from)}</div>
        <div class="reco-title"><a href="${esc(s.url || "#")}" target="_blank" rel="noopener">${esc(s.title)}</a></div>
      </div>
      <div class="reco-meta">${esc((s.authors || []).slice(0, 4).join(", "))}${s.year ? " · " + s.year : ""}${s.venue ? " · " + esc(s.venue) : ""}</div>
      <div class="reco-abs">${esc((s.abstract || s.snippet || "").slice(0, 160))}</div>
      <div class="reco-foot">
        <div class="reco-tags">
          <span class="reco-tag">${esc(s.retrieved_from || "")}</span>
          ${s.venue && s.venue !== s.retrieved_from && !s.venue.startsWith("arXiv") ? `<span class="reco-tag reco-tag-venue">${esc(s.venue)}</span>` : ""}
        </div>
        ${s.url ? `<a class="reco-trace" href="${esc(s.url)}" target="_blank" rel="noopener">🔗 溯源</a>` : ""}
      </div>
    </div>`).join("");
}
function updateSelCount() {
  const n = $$("#litResults .lit-chk:checked").length;
  $("#litSelCount").textContent = `已选 ${n} 项`;
}
function selectedLitDocs() {
  const out = [];
  $$("#litResults .lit-card").forEach((card) => {
    if (card.querySelector(".lit-chk").checked) {
      const i = parseInt(card.dataset.i);
      const s = window._litResults?.[i];
      if (s) out.push(libDocFrom(s));
    }
  });
  return out;
}
function libDocFrom(s) {
  const content = s.abstract || s.text || s.snippet || "";
  return { source_id: "", title: s.title, source_type: s.source_type || "paper",
    url: s.url || null, authors: s.authors || [], year: s.year || null, venue: s.venue || null,
    abstract: content, snippet: content.slice(0, 1500) };
}
async function litToResearch() {
  const docs = selectedLitDocs();
  if (!docs.length) return toast("请先勾选文献", true);
  state.pendingSources = docs;
  switchView("research"); showPending();
  toast(`已带入 ${docs.length} 篇文献，补充研究主题后开始`);
}
async function litSaveSel() {
  const docs = selectedLitDocs();
  if (!docs.length) return toast("请先勾选文献", true);
  let ok = 0;
  for (const d of docs) { d.folder = d.folder || libSaveFolder(); try { await fetch("/api/library", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ item: d }) }); ok++; } catch {} }
  toast(`已存入文库 ${ok} 篇`); renderLibrary();
}
async function saveOneToLibrary(s) {
  try {
    const item = libDocFrom(s);
    item.folder = item.folder || libSaveFolder();
    await fetch("/api/library", { method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ item }) });
    toast("已存入文库"); renderLibrary();
  } catch (e) { toast("保存失败：" + e.message, true); }
}

// ---------- library ----------
let libActiveFolder = "all";
const libCollapsed = new Set();   // 记录被折叠的文件夹 id（默认全部展开）
async function renderLibrary() {
  try {
    const [lib, fld] = await Promise.all([
      fetch("/api/library").then((r) => r.json()),
      fetch("/api/library/folders").then((r) => r.json()),
    ]);
    window._libItems = lib.items || [];
    window._libFolders = fld.folders || [];
    renderLibFolders();
    renderLibFiltered();
    $("#libCount").textContent = `共 ${window._libItems.length} 项`;
  } catch (e) { toast("加载文库失败", true); }
}
// ---- 文件夹树辅助 ----
function libFolderChildren(pid) {
  return (window._libFolders || []).filter((f) => (f.parent_id || "") === (pid || ""));
}
function libFolderDescendants(fid) {
  const out = new Set();
  const stack = [fid];
  while (stack.length) {
    const cur = stack.pop();
    libFolderChildren(cur).forEach((c) => { if (!out.has(c.id)) { out.add(c.id); stack.push(c.id); } });
  }
  return out;
}
function libFolderPath(fid) {
  const byId = {}; (window._libFolders || []).forEach((f) => (byId[f.id] = f));
  const path = []; let cur = byId[fid]; let guard = 0;
  while (cur && guard++ < 30) { path.unshift(cur); cur = byId[cur.parent_id || ""]; }
  return path;
}
function libFolderDepth(fid) {
  return Math.max(0, libFolderPath(fid).length - 1);
}
function libFolderCounts() {
  const folders = window._libFolders || [];
  const ids = new Set(folders.map((f) => f.id));
  const items = window._libItems || [];
  const counts = { all: items.length, uncat: 0 };
  folders.forEach((f) => {
    const sub = new Set([f.id, ...libFolderDescendants(f.id)]);
    let c = 0;
    items.forEach((it) => {
      const ef = it.folder && ids.has(it.folder) ? it.folder : "uncat";
      if (sub.has(ef)) c++;
    });
    counts[f.id] = c;
  });
  items.forEach((it) => {
    const ef = it.folder && ids.has(it.folder) ? it.folder : "未分类";
    if (!ids.has(ef)) counts.uncat++;
  });
  return counts;
}
// 整棵树的最大嵌套深度（决定颜色梯度的跨度）
function libMaxDepth() {
  let max = 0;
  const byId = {}; (window._libFolders || []).forEach((f) => (byId[f.id] = f));
  (window._libFolders || []).forEach((f) => {
    let d = 0, cur = f, guard = 0;
    while (cur && cur.parent_id && byId[cur.parent_id] && guard++ < 30) { d++; cur = byId[cur.parent_id]; }
    if (d > max) max = d;
  });
  return max;
}
// 按深度动态取色（用于面包屑文字）
function libDepthColor(depth, max) {
  const t = max > 0 ? depth / max : 0;
  const L = Math.round(40 + t * 40); // 40%(深) → 80%(浅)
  return `hsl(170, 72%, ${L}%)`;
}
// 按深度动态上色（用于侧栏文件夹行背景：根最深最浓，越往下越浅越淡）
function libDepthBg(depth, max) {
  const t = max > 0 ? depth / max : 0;
  const L = Math.round(36 + t * 44);          // 36%(深) → 80%(浅)
  const a = +(0.52 - t * 0.34).toFixed(3);    // 0.52(浓) → 0.18(淡)
  return `hsla(170, 74%, ${L}%, ${a})`;
}
// 层级引导线：目录过深时压缩显示，用省略线表示被跳过的层级，保证行宽不失控
const LIB_MAX_INDENT = 8;
function libRails(depth) {
  if (depth <= 0) return "";
  if (depth <= LIB_MAX_INDENT) {
    let r = "";
    for (let i = 0; i < depth; i++) r += `<span class="lib-rail${i === depth - 1 ? " elbow" : ""}"></span>`;
    return r;
  }
  let r = "";
  for (let i = 0; i < LIB_MAX_INDENT - 1; i++) r += `<span class="lib-rail"></span>`;
  r += `<span class="lib-rail lib-rail-skip" title="更深层级已压缩显示"></span>`;
  r += `<span class="lib-rail elbow"></span>`;
  return r;
}
function libRenderTree(pid, counts, depth, effMax, pathIds) {
  let html = "";
  libFolderChildren(pid).forEach((f) => {
    const kids = libFolderChildren(f.id);
    const hasKids = kids.length > 0;
    const expanded = !libCollapsed.has(f.id);
    const inPath = pathIds.has(f.id);
    const rails = libRails(depth);
    const bg = inPath ? libDepthBg(depth, effMax) : "transparent";
    html += `<div class="lib-folder-row${libActiveFolder === f.id ? " active" : ""}" data-f="${esc(f.id)}">
      ${rails}
      <span class="lib-entry" style="background:${bg}">
        <button class="lib-caret${hasKids ? "" : " is-empty"}" data-caret="${esc(f.id)}">${hasKids ? (expanded ? "▾" : "▸") : ""}</button>
        <button class="lib-folder" data-f="${esc(f.id)}" title="${esc(f.name)}"><span class="lib-fname">${esc(f.name)}</span><span class="lib-fc">${counts[f.id] || 0}</span></button>
      </span>
    </div>`;
    if (hasKids && expanded) html += libRenderTree(f.id, counts, depth + 1, effMax, pathIds);
  });
  return html;
}
function bindLibCrumbs(el) {
  el.querySelectorAll(".lib-crumb").forEach((c) => c.addEventListener("click", () => {
    libActiveFolder = c.dataset.f; renderLibFolders(); renderLibFiltered(); renderLibPath();
  }));
}
function renderLibPath() {
  const el = $("#libPath");
  if (!el) return;
  const maxD = libMaxDepth();
  const effMax = maxD + 1; // 与侧栏渐变保持一致（全部恒最深）
  if (libActiveFolder === "all") {
    el.innerHTML = `<span class="lib-crumb active" style="color:${libDepthColor(0, effMax)}">全部</span>`;
    return;
  }
  if (libActiveFolder === "uncat") {
    el.innerHTML = `<span class="lib-crumb" data-f="all" style="color:${libDepthColor(0, effMax)}">全部</span>` +
      `<span class="sep">/</span><span class="lib-crumb active" style="color:var(--text-dim)">未分类</span>`;
    bindLibCrumbs(el);
    return;
  }
  const path = libFolderPath(libActiveFolder);
  let html = `<span class="lib-crumb" data-f="all" style="color:${libDepthColor(0, effMax)}">全部</span>`;
  path.forEach((f, i) => {
    const isLast = i === path.length - 1;
    html += `<span class="sep">/</span><span class="lib-crumb${isLast ? " active" : ""}" data-f="${esc(f.id)}" style="color:${libDepthColor(i + 1, effMax)}">${esc(f.name)}</span>`;
  });
  el.innerHTML = html;
  bindLibCrumbs(el);
}
// 激活文件夹从根到自身的路径（用于侧栏整条路径按深度渐变上色）
// 注意：未分类是独立于"全部"的特殊分类，不并入全部路径
function libActivePathIds() {
  if (libActiveFolder === "uncat") return new Set(["uncat"]);
  if (libActiveFolder === "all" || !libActiveFolder) return new Set();
  return new Set(libFolderPath(libActiveFolder).map((f) => f.id));
}
// 当前选中的是否为"真实文件夹"（全部/未分类不可重命名或删除）
function libActiveIsReal() {
  return !!libActiveFolder && libActiveFolder !== "all" && libActiveFolder !== "uncat"
    && (window._libFolders || []).some((x) => x.id === libActiveFolder);
}
function libActiveFolderName() {
  if (libActiveFolder === "all") return "全部";
  if (libActiveFolder === "uncat") return "未分类";
  const f = (window._libFolders || []).find((x) => x.id === libActiveFolder);
  return f ? f.name : "";
}
function renderLibFolders() {
  const counts = libFolderCounts();
  const maxD = libMaxDepth();
  const effMax = maxD + 1; // 让"全部"(0) 比最浅文件夹更深
  const pathIds = libActivePathIds();
  const allBg = libDepthBg(0, effMax); // 全部恒为最深绿（根）
  // 未分类是独立特殊分类，用浅灰而非绿，点选时浅灰高亮
  const uncatBg = libActiveFolder === "uncat" ? "hsla(220, 9%, 55%, 0.18)" : "transparent";
  let html = `<button class="lib-folder lib-root${libActiveFolder === "all" ? " active" : ""}" data-f="all" style="background:${allBg}"><span class="lib-fname">📚 全部</span><span class="lib-fc">${counts.all || 0}</span></button>`;
  html += libRenderTree("", counts, 1, effMax, pathIds);
  html += `<button class="lib-folder lib-root${libActiveFolder === "uncat" ? " active" : ""}" data-f="uncat" style="background:${uncatBg}"><span class="lib-fname">🗂 未分类</span><span class="lib-fc">${counts.uncat}</span></button>`;
  const box = $("#libFolders");
  box.innerHTML = html;
  box.querySelectorAll(".lib-folder").forEach((b) =>
    b.addEventListener("click", () => { libActiveFolder = b.dataset.f; renderLibFolders(); renderLibFiltered(); renderLibPath(); }));
  box.querySelectorAll(".lib-caret").forEach((b) =>
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      const id = b.dataset.caret;
      if (libCollapsed.has(id)) libCollapsed.delete(id); else libCollapsed.add(id);
      renderLibFolders();
    }));
  // 顶栏操作按钮可用性：仅当选中真实文件夹时可重命名/删除
  const real = libActiveIsReal();
  const renBtn = $("#libRenFolder"), delBtn = $("#libDelFolder");
  if (renBtn) renBtn.disabled = !real;
  if (delBtn) delBtn.disabled = !real;
  renderLibPath();
}
// 移动：弹窗内以显式文件夹目录树选择目标文件夹
function openLibMoveModal() {
  const n = $$("#libList .lib-card .lib-chk:checked").length;
  if (!n) { toast("请先勾选要移动的资料", true); return; }
  window._libMoveTarget = "";
  renderLibMoveTree();
  $("#libMoveModal").classList.remove("hidden");
}
function closeLibMoveModal() { $("#libMoveModal").classList.add("hidden"); }
function renderLibMoveTree() {
  const maxD = libMaxDepth();
  const effMax = maxD + 1;
  const sel = window._libMoveTarget || "";
  // 完整复刻侧栏目录：全部（根）→ 全部文件夹树（含子级，已展开）→ 未分类
  let html = `<button class="lib-move-item${sel === "all" ? " sel" : ""}" data-t="all">📚 全部</button>`;
  (function walk(pid, depth) {
    libFolderChildren(pid).forEach((f) => {
      const rails = libRails(depth);
      html += `<button class="lib-move-item${sel === f.id ? " sel" : ""}" data-t="${esc(f.id)}" title="${esc(f.name)}">${rails}<span class="lib-mname">${esc(f.name)}</span></button>`;
      walk(f.id, depth + 1);
    });
  })("", 1);
  html += `<button class="lib-move-item${sel === "uncat" ? " sel" : ""}" data-t="uncat">🗂 未分类</button>`;
  const box = $("#libMoveTree");
  box.innerHTML = html;
  box.querySelectorAll(".lib-move-item").forEach((b) => b.addEventListener("click", () => {
    window._libMoveTarget = b.dataset.t;
    box.querySelectorAll(".lib-move-item").forEach((x) => x.classList.remove("sel"));
    b.classList.add("sel");
  }));
}
function openNewFolderModal(parentId) {
  libFillFolderParent($("#libFolderParent"), parentId || "");
  $("#libFolderName").value = "";
  $("#libFolderModal").classList.remove("hidden");
  setTimeout(() => { const i = $("#libFolderName"); if (i) i.focus(); }, 0);
}
function closeNewFolderModal() {
  $("#libFolderModal").classList.add("hidden");
}
function libFillFolderParent(sel, selected) {
  let html = `<option value="">（根目录）</option>`;
  (function walk(pid, depth) {
    libFolderChildren(pid).forEach((f) => {
      const sel = (f.id === selected) ? " selected" : "";
      html += `<option value="${esc(f.id)}"${sel}>${" ".repeat(depth)}${esc(f.name)}</option>`;
      walk(f.id, depth + 1);
    });
  })("", 0);
  sel.innerHTML = html;
}
async function createFolder() {
  const name = ($("#libFolderName").value || "").trim();
  if (!name) { toast("请输入文件夹名称", true); return; }
  const parent = $("#libFolderParent").value || "";
  closeNewFolderModal();
  try {
    await fetch("/api/library/folders", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, parent_id: parent }) });
    renderLibrary();
  } catch (e) { toast("新建文件夹失败", true); }
}
async function renFolder(fid, old) {
  const name = prompt("重命名文件夹：", old);
  if (!name || !name.trim() || name.trim() === old) return;
  try {
    await fetch("/api/library/folders/" + fid, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: name.trim() }) });
    renderLibrary();
  } catch (e) { toast("重命名失败", true); }
}
async function delFolder(fid, name) {
  const sub = libFolderDescendants(fid); sub.add(fid);
  const msg = sub.size > 1
    ? `删除文件夹「${name}」及其 ${sub.size - 1} 个子文件夹？其中的文献将移至「未分类」。`
    : `删除文件夹「${name}」？其中的文献将移至「未分类」。`;
  if (!confirm(msg)) return;
  try {
    await fetch("/api/library/folders/" + fid, { method: "DELETE" });
    if (sub.has(libActiveFolder)) libActiveFolder = "all";
    renderLibrary();
  } catch (e) { toast("删除失败", true); }
}
async function confirmLibMove() {
  const target = window._libMoveTarget;
  if (!target) return toast("请选择目标文件夹", true);
  const ids = [];
  $$("#libList .lib-card").forEach((card) => {
    if (card.querySelector(".lib-chk").checked) {
      const it = window._libView?.[parseInt(card.dataset.i)];
      if (it) ids.push(it.saved_id);
    }
  });
  if (!ids.length) { closeLibMoveModal(); return toast("请先勾选资料", true); }
  const folder = (target === "uncat" || target === "all") ? "" : target;
  try {
    await fetch("/api/library/move", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids, folder }) });
    toast(`已移动 ${ids.length} 项`);
    closeLibMoveModal();
    renderLibrary();
  } catch (e) { toast("移动失败", true); }
}
function renderLibFiltered() {
  const items = window._libItems || [];
  const folders = window._libFolders || [];
  const ids = new Set(folders.map((f) => f.id));
  const kw = ($("#libSearch").value || "").trim().toLowerCase();
  const type = $("#libType").value;
  const sort = $("#libSort").value;
  let arr = items.filter((it) => {
    const ef = it.folder && ids.has(it.folder) ? it.folder : "uncat";
    if (libActiveFolder !== "all") {
      if (libActiveFolder === "uncat") { if (ef !== "uncat") return false; }
      else {
        const sub = new Set([libActiveFolder, ...libFolderDescendants(libActiveFolder)]);
        if (!sub.has(ef)) return false;
      }
    }
    if (type && (it.source_type || "paper") !== type) return false;
    if (kw) {
      const hay = ((it.title || "") + " " + (it.authors || []).join(" ")).toLowerCase();
      if (!hay.includes(kw)) return false;
    }
    return true;
  });
  if (sort === "title") arr = arr.slice().sort((a, b) => (a.title || "").localeCompare(b.title || ""));
  else if (sort === "year") arr = arr.slice().sort((a, b) => (b.year || 0) - (a.year || 0));
  else if (sort === "old") arr = arr.slice().sort((a, b) => (a.saved_at || "").localeCompare(b.saved_at || ""));
  else arr = arr.slice().sort((a, b) => (b.saved_at || "").localeCompare(a.saved_at || ""));
  window._libView = arr;
  const box = $("#libList");
  if (!arr.length) { box.innerHTML = `<div class="empty">没有匹配的文献。</div>`; return; }
  box.innerHTML = arr.map((it, i) => {
    const fname = (it.folder && folders.find((f) => f.id === it.folder))?.name || "未分类";
    const isUpload = it.source_type === "upload";
    return `<div class="lib-card" data-i="${i}">
      <div class="lib-card-top">
        <input type="checkbox" class="lib-chk" />
        <span class="lib-type-tag ${isUpload ? "lib-type-upload" : "lib-type-paper"}">${isUpload ? "本地文档" : "论文"}</span>
        <div class="lib-title">${it.url ? `<a href="${esc(it.url)}" target="_blank">${esc(it.title)}</a>` : esc(it.title)}</div>
        <div class="lib-aside">
          <span class="lib-folder-tag">${esc(fname)}</span>
          <button class="lib-del" title="删除">✕</button>
        </div>
      </div>
      <div class="lib-meta">${esc((it.authors || []).slice(0, 4).join(", "))}${it.year ? " · " + it.year : ""}${it.venue ? " · " + esc(it.venue) : ""}</div>
      <div class="lib-abs">${esc((it.abstract || it.text || ""))}</div>
    </div>`;
  }).join("");
  box.querySelectorAll(".lib-chk").forEach((c) => c.addEventListener("change", updateLibCount));
  box.querySelectorAll(".lib-del").forEach((b, i) => b.addEventListener("click", () => delLib(arr[i].saved_id)));
}
function updateLibCount() {
  const n = $$("#libList .lib-chk:checked").length;
  $("#libCount").textContent = `已选 ${n} 项` + (window._libItems ? ` · 共 ${window._libItems.length} 项` : "");
}
function selectedLibDocs() {
  const out = [];
  $$("#libList .lib-card").forEach((card) => {
    if (card.querySelector(".lib-chk").checked) {
      const it = window._libView?.[parseInt(card.dataset.i)];
      if (it) out.push(libDocFrom(it));
    }
  });
  return out;
}
async function libToResearch() {
  const docs = selectedLibDocs();
  if (!docs.length) return toast("请先勾选资料", true);
  state.pendingSources = docs;
  switchView("research"); showPending();
  toast(`已带入 ${docs.length} 项资料，补充研究主题后开始`);
}
async function delLib(id) {
  try { await fetch("/api/library/" + id, { method: "DELETE" }); toast("已删除"); renderLibrary(); }
  catch (e) { toast("删除失败", true); }
}
function libSaveFolder() {
  return (libActiveFolder !== "all" && libActiveFolder !== "uncat") ? libActiveFolder : "";
}
// 侧栏宽度可拖拽（左右拉）；侧栏与列表本身可滚动（上下拉）
function initLibResizer() {
  const rz = $("#libResizer");
  const side = $(".lib-side");
  if (!rz || !side) return;
  let dragging = false;
  rz.addEventListener("pointerdown", (e) => {
    dragging = true;
    try { rz.setPointerCapture(e.pointerId); } catch (_) {}
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  });
  rz.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const layout = rz.closest(".lib-layout");
    const rect = layout.getBoundingClientRect();
    let w = e.clientX - rect.left;
    if (w < 180) w = 180;
    if (w > 460) w = 460;
    side.style.width = w + "px";
  });
  const stop = (e) => {
    if (!dragging) return;
    dragging = false;
    try { rz.releasePointerCapture(e.pointerId); } catch (_) {}
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  };
  rz.addEventListener("pointerup", stop);
  rz.addEventListener("pointercancel", stop);
}
async function libUpload() {
  const input = $("#libFile");
  const files = [...input.files];
  if (!files.length) return;
  const folder = libSaveFolder();
  let ok = 0, fail = 0;
  for (const f of files) {
    const fd = new FormData(); fd.append("file", f);
    try {
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      if (!r.ok) throw new Error((await r.json()).detail || "上传失败");
      const d = await r.json();
      if (!(d.text || "").trim()) throw new Error("未能提取文本（请确认是文本型 PDF / TXT / MD）");
      await fetch("/api/library", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item: { title: d.filename, source_type: "upload", url: null,
          authors: [], year: null, venue: "本地文档", abstract: (d.text || "").slice(0, 800),
          text: d.text || "", retrieved_from: "上传", folder } }) });
      ok++;
      toast(`已存入文库：${d.filename}`);
    } catch (e) { fail++; toast(`${f.name}：${e.message}`, true); }
  }
  input.value = "";
  if (ok) toast(`上传完成：成功 ${ok}${fail ? `，失败 ${fail}` : ""} 个`);
  renderLibrary();
}

// ---------- history (unified across 4 modules) ----------
let histSelMode = false; // 是否处于"选择删除"模式
async function renderHistory() {
  try {
    const r = await fetch("/api/history");
    const d = await r.json();
    window._history = d.items || [];
    renderHistoryList("all");
  } catch (e) { toast("加载历史失败", true); }
}
function renderHistoryList(kind) {
  const all = window._history || [];
  const filtered = all
    .map((h, gi) => ({ h, gi }))
    .filter(({ h }) => kind === "all" || h.kind === kind || (kind === "search" && h.kind === "smart"));
  const box = $("#histList");
  box.classList.toggle("sel-mode", histSelMode);
  if (!filtered.length) { box.innerHTML = `<div class="empty">该模块暂无历史记录。</div>`; return; }
  const labelMap = { research: "深度研究", search: "文献检索", smart: "智能检索", paper: "论文研讨", studio: "写作助手", advisor: "思路提炼" };
  box.innerHTML = filtered.map(({ h, gi }) => `
    <div class="hist-card" data-gi="${gi}">
      <input type="checkbox" class="h-chk" />
      <div class="h-body">
        <div class="h-q">${esc(h.title)}</div>
        <div class="h-meta">
          <span class="h-badge h-${h.kind}">${labelMap[h.kind] || h.kind}</span>
          <span>${esc(h.sub || "")}</span>
          <span>${fmtTs(h.ts)}</span>
        </div>
        ${h.snippet ? `<div class="h-snip">${esc(h.snippet)}</div>` : ""}
      </div>
    </div>`).join("");
  box.querySelectorAll(".hist-card").forEach((c) => {
    const chk = c.querySelector(".h-chk");
    c.addEventListener("click", (e) => {
      if (histSelMode) {
        if (e.target !== chk) chk.checked = !chk.checked; // 点卡片切换，点复选框本身不重复切换
        c.classList.toggle("sel", chk.checked);
        updateHistSelCount();
      } else {
        openHistory(parseInt(c.dataset.gi));
      }
    });
    chk.addEventListener("change", () => { c.classList.toggle("sel", chk.checked); updateHistSelCount(); });
  });
  updateHistSelCount();
}
function updateHistSelCount() {
  const n = $$("#histList .h-chk:checked").length;
  const el = $("#histSelCount"); if (el) el.textContent = n;
  const del = $("#histDelSel"); if (del) del.disabled = n === 0;
}
function toggleHistSelMode() {
  histSelMode = !histSelMode;
  $("#histSelectBtn").textContent = histSelMode ? "完成" : "选择删除";
  $("#histBulk").classList.toggle("hidden", !histSelMode);
  $("#histList").classList.toggle("sel-mode", histSelMode);
  if (!histSelMode) {
    $$("#histList .h-chk").forEach((c) => (c.checked = false));
    $$("#histList .hist-card").forEach((c) => c.classList.remove("sel"));
  }
  updateHistSelCount();
}
function histSelectAll(checked) {
  $$("#histList .h-chk").forEach((c) => (c.checked = checked));
  $$("#histList .hist-card").forEach((c) => c.classList.toggle("sel", checked));
  updateHistSelCount();
}
async function histDelSelected() {
  const items = [];
  $$("#histList .hist-card").forEach((c) => {
    const chk = c.querySelector(".h-chk");
    if (chk && chk.checked) {
      const h = (window._history || [])[parseInt(c.dataset.gi)];
      if (h) items.push({ kind: h.kind, id: h.id, advisor_id: h.advisor_id, ts: h.ts, query: h.query, paper_id: h.paper_id, tool: h.tool });
    }
  });
  if (!items.length) return toast("请先勾选要删除的历史", true);
  if (!confirm(`确定删除选中的 ${items.length} 条历史记录？此操作不可恢复。`)) return;
  try {
    await fetch("/api/history", { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items }) });
    toast(`已删除 ${items.length} 条`);
    histSelMode = false;
    $("#histSelectBtn").textContent = "选择删除";
    $("#histBulk").classList.add("hidden");
    $("#histList").classList.remove("sel-mode");
    renderHistory();       // 重新拉取历史列表
    renderRightRail();     // 同步刷新右栏『最近动态』，避免删除后还显示
  } catch (e) { toast("删除失败", true); }
}
async function openHistory(gi) {
  const h = (window._history || [])[gi];
  if (!h) return;
  try {
    if (h.kind === "research") {
      const r = await fetch("/api/task/" + h.id);
      if (!r.ok) throw new Error("任务不存在");
      const t = await r.json();
      switchView("research");
      loadTaskIntoWorkspace(t);
    } else if (h.kind === "search" || h.kind === "smart") {
      switchView("search");
      $("#litQuery").value = h.query || h.title;
      toast("已填入检索框，点击「检索」可重新检索");
    } else if (h.kind === "studio") {
      switchView("studio");
      renderStudioTools();
      const first = $("#studioFields .lit-input");
      if (first) first.value = h.title;
      toast("已切换到写作助手");
    } else if (h.kind === "paper") {
      openPaperHistory(h);
    } else if (h.kind === "advisor") {
      openAdvisorHistory(h);
    }
  } catch (e) { toast(e.message, true); }
}

// 从历史 / 最近动态点回一段思路提炼对话，恢复现场并支持继续推演
function openAdvisorHistory(h) {
  switchView("advisor");
  state.advisorId = h.advisor_id || null;
  state.advisorHistory = (h.transcript || []).slice();
  state._autoEvidenceTopic = null;
  const box = $("#advisorMessages");
  box.innerHTML = "";
  if (!state.advisorHistory.length) {
    box.innerHTML = `<div class="empty">描述你的研究兴趣或卡点，例如：「我想做医疗 RAG 的上下文压缩，但不知道从哪个点切入。」</div>`;
  } else {
    state.advisorHistory.forEach((m) => {
      const el = appendAdvisorMsg(m.role, m.content);
      if (m.role === "assistant") {
        const a = el.querySelector(".advisor-actions");
        if (a) { a.style.display = "flex"; delete a.dataset.pending; }
        const mb = el.querySelector(".advisor-body");
        if (mb) mb.style.paddingBottom = "";
      }
    });
  }
  // 复位指南 / 检索依据子窗口
  state.advisorGuideMd = "";
  $("#advisorGuideBody").innerHTML = `<div class="empty">在左侧对话中梳理思路后，点击「生成指南」导出一份结构化思路提炼结果。指南会按<strong>已锚定的研究要素</strong>与<strong>待论证的研究要素</strong>两组沉淀。</div>`;
  $("#advisorGuideActions").classList.add("hidden");
  $("#advisorEvidenceLog").innerHTML = `<div class="empty">与专业相关的论断会<strong>先检索真实文献、再结合引用作答</strong>，检索过程与结果同步到右侧「本次引用」。</div>`;
  $("#advisorEvidenceList").innerHTML = "";
  window.advisorEvidence = [];
  renderRightCitations();
  toast("已载入该思路提炼对话，可继续推演");
}

// ---------- writing studio ----------
// 各写作工具及其所需输入字段（按工具动态渲染，不依赖文库）
const STUDIO_TOOLS = [
  { id: "abstract", label: "摘要生成", desc: "根据论文全文或核心内容，生成一段结构化的学术摘要。",
    fields: [
      { id: "fulltext", label: "论文全文 / 核心内容", type: "textarea", rows: 6, ph: "粘贴论文全文，或背景、方法、结论等关键内容……", required: true },
      { id: "keywords", label: "关键词（可选）", type: "text", ph: "如：多模态, 检索增强生成, RAG", required: false },
    ] },
  { id: "outline", label: "提纲生成", desc: "围绕研究主题生成一份层级化、可落地的报告提纲。",
    fields: [
      { id: "topic", label: "研究主题 / 方向", type: "text", ph: "如：大语言模型在自动化文献综述中的应用", required: true },
      { id: "scope", label: "范围 / 侧重点（可选）", type: "text", ph: "如：聚焦近 3 年方法，面向中文场景", required: false },
      { id: "sections", label: "期望章节数（可选）", type: "text", ph: "如：7", required: false },
    ] },
  { id: "paragraph", label: "单段综述", desc: "基于你提供的文献要点，撰写一段条理清晰的综述段落。",
    fields: [
      { id: "topic", label: "综述主题", type: "text", ph: "如：检索器的多路召回与重排", required: true },
      { id: "notes", label: "文献要点 / 笔记", type: "textarea", rows: 6, ph: "每条写清方法 / 结论，可多列几条……", required: true },
    ] },
  { id: "rq", label: "研究问题", desc: "从领域现状中提炼出有价值、可研究的问题。",
    fields: [
      { id: "topic", label: "研究领域", type: "text", ph: "如：代码大模型", required: true },
      { id: "status", label: "现有工作摘要（可选）", type: "textarea", rows: 4, ph: "简述已有进展与不足……", required: false },
    ] },
  { id: "contributions", label: "贡献点提炼", desc: "从草稿 / 方法描述中提炼清晰的论文贡献。",
    fields: [
      { id: "draft", label: "论文草稿 / 方法描述", type: "textarea", rows: 6, ph: "粘贴你的方法、实验或核心思路……", required: true },
    ] },
  { id: "title", label: "论文标题", desc: "基于摘要生成多个风格各异的候选标题。",
    fields: [
      { id: "abstract", label: "摘要 / 核心内容", type: "textarea", rows: 5, ph: "粘贴摘要或核心贡献……", required: true },
      { id: "style", label: "偏好风格（可选）", type: "text", ph: "如：方法型、问题型、简洁", required: false },
    ] },
  { id: "intro", label: "引言段落", desc: "从背景自然过渡到本文目标，写一段有真实依据的引言（需提供相关文献）。",
    fields: [
      { id: "background", label: "研究背景", type: "textarea", rows: 3, ph: "宏观背景与领域现状……", required: true },
      { id: "problem", label: "待解决的问题", type: "text", ph: "本文要攻克的核心问题", required: true },
      { id: "method", label: "方法概要", type: "text", ph: "你的解决思路 / 方法", required: true },
      { id: "refs", label: "相关文献及其说明（用于真实引用，必填）", type: "textarea", rows: 5,
        ph: "逐条列出相关文献：作者/年份、核心贡献、与本文的关系。如：[1] Smith 2023 提出 X 解决了 Y，但忽略了 Z，本文正针对 Z。……", required: true },
    ] },
  { id: "related", label: "相关工作", desc: "基于你提供的文献清单，撰写一段有真实依据的『相关工作 / Related Work』综述。",
    fields: [
      { id: "topic", label: "研究主题 / 方向", type: "text", ph: "如：大语言模型的检索增强生成（RAG）", required: true },
      { id: "refs", label: "相关文献及其说明（必填）", type: "textarea", rows: 7,
        ph: "逐条列出相关文献：作者/年份、标题、核心方法或结论、局限，以及它们之间的关系。如：[1] Lewis 2020 提出 RAG，将检索器与生成器拼接……[2] ……", required: true },
    ] },
  { id: "keywords", label: "关键词提取", desc: "从摘要中提取中英文关键词。",
    fields: [
      { id: "abstract", label: "摘要", type: "textarea", rows: 4, ph: "粘贴论文摘要……", required: true },
    ] },
];
function renderStudioTools() {
  const bar = $("#studioToolbar");
  bar.innerHTML = STUDIO_TOOLS.map((t) =>
    `<button class="tool-tab${t.id === state.currentTool ? " active" : ""}" data-tool="${t.id}">${t.label}</button>`).join("");
  bar.querySelectorAll(".tool-tab").forEach((b) => b.addEventListener("click", () => {
    $$("#studioToolbar .tool-tab").forEach((x) => x.classList.toggle("active", x === b));
    state.currentTool = b.dataset.tool;
    renderStudioFields();
  }));
  renderStudioFields();
}
function renderStudioFields() {
  const t = STUDIO_TOOLS.find((x) => x.id === state.currentTool) || STUDIO_TOOLS[0];
  $("#studioToolDesc").textContent = t.desc;
  const box = $("#studioFields");
  box.innerHTML = t.fields.map((f) => {
    const cid = "stf_" + f.id;
    const ctrl = f.type === "textarea"
      ? `<textarea id="${cid}" class="lit-input" rows="${f.rows || 4}" placeholder="${esc(f.ph || "")}"></textarea>`
      : `<input id="${cid}" class="lit-input" placeholder="${esc(f.ph || "")}" />`;
    return `<div class="studio-field"><label class="studio-fl">${esc(f.label)}${f.required ? ' <span class="req">*</span>' : ""}</label>${ctrl}</div>`;
  }).join("");
}
function collectStudioInputs() {
  const t = STUDIO_TOOLS.find((x) => x.id === state.currentTool) || STUDIO_TOOLS[0];
  const parts = [];
  for (const f of t.fields) {
    const v = ($("#stf_" + f.id).value || "").trim();
    if (v) parts.push(`【${f.label}】\n${v}`);
    else if (f.required) return { error: `请填写：${f.label}` };
  }
  return { topic: parts.join("\n\n") };
}
async function runTool() {
  const collected = collectStudioInputs();
  if (collected.error) return toast(collected.error, true);
  const box = $("#studioOutput");
  box.innerHTML = `<div class="empty">生成中…</div>`;
  $("#studioCopyBtn").classList.add("hidden");
  state.studioMd = "";
  try {
    const resp = await fetch("/api/tools/run", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool: state.currentTool, topic: collected.topic, language: $("#language").value }) });
    if (!resp.ok) throw new Error("请求失败：" + resp.status);
    let html = "";
    await consumeSSE(resp.body, (ev, data) => {
      if (ev === "tool_delta") { html += data.delta; box.innerHTML = renderMarkdown(html); box.scrollTop = box.scrollHeight; }
      else if (ev === "error") toast(data.message, true);
    });
    state.studioMd = html;
    const plain = html.replace(/[#>*_`\-\n]/g, " ").replace(/\s+/g, " ").trim();
    fetch("/api/studio/history", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: plain.slice(0, 60), tool: state.currentTool, snippet: plain.slice(0, 200) }) }).catch(() => {});
    renderRightRail();
    if (html.trim()) $("#studioCopyBtn").classList.remove("hidden");
  } catch (e) { toast(e.message, true); }
}

// ---------- settings ----------
async function loadSettings() {
  try {
    const r = await fetch("/api/settings");
    const d = await r.json();
    const def = d.defaults || {};
    if (def.depth) $("#depth").value = def.depth;
    if (def.style) $("#style").value = def.style;
    if (def.language) $("#language").value = def.language;
    if (def.task_type && $("#taskType")) $("#taskType").value = def.task_type;
    if (def.cite_count != null && $("#citeCount")) $("#citeCount").value = def.cite_count;
    updateHint();
  } catch {}
}
async function renderSettings() {
  try {
    const r = await fetch("/api/settings");
    const d = await r.json();
    const conn = $("#connStatus");
    if (d.configured) { conn.textContent = "● 已连接：" + d.model; conn.className = "conn-status ok"; }
    else { conn.textContent = "● 未配置 API Key（请在 .env 填入 HY3_API_KEY）"; conn.className = "conn-status err"; }
    $("#setModel").textContent = d.model || "–";
    $("#setBase").textContent = d.base_url || "–";
    const ss = d.source_status || {};
    $("#setSources").innerHTML = Object.entries(ss).map(([k,v]) => `<div>${k}：${esc(v)}</div>`).join("");
    const def = d.defaults || {};
    if (def.depth) $("#setDepth").value = def.depth;
    if (def.style) $("#setStyle").value = def.style;
    if (def.language) $("#setLang").value = def.language;
    if (def.task_type && $("#setTaskType")) $("#setTaskType").value = def.task_type;
    if (def.cite_count != null && $("#setCiteCount")) $("#setCiteCount").value = def.cite_count;
    const srcs = def.sources || [];
    $$(".srcChk").forEach((c) => (c.checked = srcs.includes(c.value)));
    const rcEl = $("#setRecentCount");
    if (rcEl) { const rc = parseInt(localStorage.getItem("hy3-recent-count"), 10); rcEl.value = rc > 0 ? rc : 6; }
  } catch (e) { toast("加载设置失败", true); }
}
async function saveSettings() {
  const sources = [...$$(".srcChk:checked")].map((c) => c.value);
  const body = { depth: $("#setDepth").value, style: $("#setStyle").value,
    language: $("#setLang").value, sources,
    task_type: $("#setTaskType") ? $("#setTaskType").value : undefined,
    cite_count: $("#setCiteCount") ? (parseInt($("#setCiteCount").value, 10) || 0) : undefined };
  // 最近动态显示条数（本地保存，立即生效）
  const rcEl = $("#setRecentCount");
  if (rcEl) {
    let rc = parseInt(rcEl.value, 10);
    if (!(rc > 0)) rc = 6;
    rc = Math.min(30, Math.max(1, rc));
    rcEl.value = rc;
    localStorage.setItem("hy3-recent-count", rc);
    renderRightRail();
  }
  try {
    const r = await fetch("/api/settings", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(body) });
    if (!r.ok) throw new Error("保存失败");
    const d = await r.json();
    const def = d.defaults || {};
    if (def.depth) $("#depth").value = def.depth;
    if (def.style) $("#style").value = def.style;
    if (def.language) $("#language").value = def.language;
    if (def.task_type && $("#taskType")) $("#taskType").value = def.task_type;
    if (def.cite_count != null && $("#citeCount")) { $("#citeCount").value = def.cite_count; }
    updateHint();
    $("#settingsMsg").textContent = "✓ 已保存默认设置";
    setTimeout(() => ($("#settingsMsg").textContent = ""), 2500);
  } catch (e) { toast(e.message, true); }
}

// ---------- profile（个人主页 · 研究者档案 + 研究兴趣，用于推荐） ----------
const PF_AVATARS = ["🧑‍🔬", "👩‍🔬", "👨‍🎓", "👩‍🎓", "🧑‍💻", "👨‍🏫", "👩‍🏫", "🧠", "📚", "🚀", "🔬", "🦉"];
const PF_INTEREST_PRESETS = [
  "大语言模型（LLM）", "检索增强生成（RAG）", "多模态学习", "智能体（Agent）", "知识图谱",
  "自然语言处理", "计算机视觉", "强化学习", "图神经网络", "AI for Science",
  "推荐系统", "信息检索", "可解释性", "模型压缩与推理加速",
];
let pfInterests = [];
let pfAvatar = "🧑‍🔬";

function renderAvatar() {
  const el = $("#pfAvatar");
  if (!el) return;
  if (typeof pfAvatar === "string" && pfAvatar.startsWith("data:image")) {
    el.innerHTML = `<img src="${pfAvatar}" alt="头像" />`;
  } else {
    el.textContent = pfAvatar || "🧑‍🔬";
  }
}
function renderProfileAvatars() {
  const box = $("#pfAvatarPick");
  if (!box) return;
  box.innerHTML = PF_AVATARS.map((a) =>
    `<button type="button" class="pf-av-opt ${a === pfAvatar ? "active" : ""}" data-v="${a}">${a}</button>`
  ).join("");
}
function renderInterestChips() {
  const box = $("#pfInterests");
  if (box) {
    box.innerHTML = pfInterests.length
      ? pfInterests.map((v) =>
          `<span class="pf-tag">${esc(v)}<button type="button" class="pf-tag-x" data-v="${esc(v)}" title="移除">✕</button></span>`
        ).join("")
      : `<span class="pf-tags-empty">还没有添加研究兴趣，添加后可获得更贴合的推荐。</span>`;
  }
  const sg = $("#pfInterestSuggest");
  if (sg) {
    const rest = PF_INTEREST_PRESETS.filter((p) => !pfInterests.includes(p));
    sg.innerHTML = rest.map((p) => `<button type="button" class="pf-preset chip" data-v="${esc(p)}">＋ ${esc(p)}</button>`).join("");
  }
}
function addInterest(raw) {
  const v = (raw || "").trim();
  if (!v) return;
  if (pfInterests.includes(v)) return toast("该兴趣已添加", true);
  if (pfInterests.length >= 20) return toast("研究兴趣最多 20 个", true);
  pfInterests.push(v);
  renderInterestChips();
}
function removeInterest(v) {
  pfInterests = pfInterests.filter((x) => x !== v);
  renderInterestChips();
}
async function renderProfile() {
  try {
    const r = await fetch("/api/settings");
    const d = await r.json();
    const p = d.profile || {};
    pfAvatar = p.avatar || "🧑‍🔬";
    pfInterests = Array.isArray(p.interests) ? p.interests.slice() : [];
    renderAvatar();
    $("#pfName").value = p.name || "";
    $("#pfRole").value = p.role || "";
    $("#pfOrg").value = p.org || "";
    $("#pfField").value = p.field || "";
    $("#pfBio").value = p.bio || "";
    renderProfileAvatars();
    renderInterestChips();
  } catch (e) { toast("加载个人主页失败", true); }
}
async function saveProfile() {
  const profile = {
    avatar: pfAvatar,
    name: $("#pfName").value.trim(),
    role: $("#pfRole").value,
    org: $("#pfOrg").value.trim(),
    field: $("#pfField").value.trim(),
    interests: pfInterests.slice(),
    bio: $("#pfBio").value.trim(),
  };
  try {
    const r = await fetch("/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile }),
    });
    if (!r.ok) throw new Error("保存失败");
    const d = await r.json();
    if (d.profile && Array.isArray(d.profile.interests)) {
      pfInterests = d.profile.interests.slice();
      renderInterestChips();
    }
    $("#pfMsg").textContent = "✓ 已保存个人主页，推荐将结合你的研究兴趣更新";
    setTimeout(() => ($("#pfMsg").textContent = ""), 2800);
    loadSuggestions(); // 兴趣变化后刷新「猜你想搜 / 推荐研究」
  } catch (e) { toast(e.message, true); }
}

// ---------- paper discussion (interactive PDF seminar) ----------
async function paperUpload() {
  const f = $("#paperFile").files[0];
  if (!f) return toast("请选择论文文件", true);
  const fd = new FormData(); fd.append("file", f);
  $("#paperStatus").textContent = "解析中…";
  try {
    const r = await fetch("/api/paper/upload", { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail || "上传失败");
    const d = await r.json();
    state.paperId = d.paper_id; state.paperHistory = [];
    $("#paperTitle").textContent = d.filename + (d.trunc_note ? " " + d.trunc_note : "");
    closeFlowModal();
    $("#paperSetup").classList.add("hidden");
    $("#paperEmpty").classList.add("hidden");
    $("#paperChat").classList.remove("hidden");
    $("#paperMessages").innerHTML = `<div class="empty">论文已就绪，开始提问吧。</div>`;
    toast(`已解析 ${d.filename}（${d.chars} 字）`);
  } catch (e) { toast(e.message, true); $("#paperStatus").textContent = "解析失败：" + e.message; }
}
function copyText(text, btn) {
  if (!text) return toast("没有可复制的内容", true);
  const done = () => {
    if (btn) { const o = btn.textContent; btn.textContent = "✓ 已复制"; setTimeout(() => (btn.textContent = o), 1200); }
    toast("已复制到剪贴板（Markdown / 文本）");
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else fallbackCopy(text, done);
}
// 复制论文研讨对话（含用户提问与 Hy3 回答）
function copyPaperChat() {
  const msgs = $$("#paperMessages .paper-msg");
  if (!msgs.length) return toast("暂无对话可复制", true);
  const lines = [];
  msgs.forEach((m) => {
    const text = (m._text || "").trim();
    if (!text) return;
    const who = m.dataset.role === "user" ? "我" : "Hy3";
    lines.push(`${who}：${text}`);
  });
  if (!lines.length) return toast("暂无对话可复制", true);
  copyText(lines.join("\n\n"), $("#paperCopyBtn"));
}
function fallbackCopy(text, done) {
  const ta = document.createElement("textarea");
  ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); done(); } catch (e) { toast("复制失败", true); }
  document.body.removeChild(ta);
}
// 把当前 DOM 中的消息同步回 state.paperHistory（以原始文本为准）
function syncPaperHistoryFromDOM() {
  const hist = [];
  $$("#paperMessages .paper-msg").forEach((m) => {
    const role = m.dataset.role, text = m._text || "";
    if (role && text) hist.push({ role, content: text });
  });
  state.paperHistory = hist;
}
function appendPaperMsg(role, text) {
  const box = $("#paperMessages");
  const empty = box.querySelector(".empty"); if (empty) empty.remove();
  const el = document.createElement("div");
  el.className = "paper-msg " + role;
  el.dataset.role = role;
  el._text = text || "";
  const body = document.createElement("div");
  body.className = "pm-body";
  const content = document.createElement("div");
  content.className = "pm-content";
  content.innerHTML = text ? renderMarkdown(text) : "";
  const actions = document.createElement("div");
  actions.className = "pm-actions";
  if (role === "user") {
    const edit = document.createElement("button");
    edit.className = "pm-btn pm-edit"; edit.textContent = "✎ 修改"; edit.title = "把这条消息填入输入框，修改后重新发送";
    edit.addEventListener("click", () => { $("#paperInput").value = el._text; $("#paperInput").focus(); });
    actions.appendChild(edit);
  } else {
    // 复制 / 重新生成按钮等消息完整生成后再显示
    actions.style.display = "none";
    actions.dataset.pending = "1";
    body.style.paddingBottom = "14px";
    const regen = document.createElement("button");
    regen.className = "pm-btn pm-regen"; regen.textContent = "↻ 重新生成"; regen.title = "基于相同上文重新生成这条回复";
    regen.addEventListener("click", () => regeneratePaper(el));
    const copy = document.createElement("button");
    copy.className = "pm-btn pm-copy"; copy.textContent = "复制"; copy.title = "复制为 Markdown / 文本";
    copy.addEventListener("click", () => copyText(el._text, copy));
    actions.appendChild(regen); actions.appendChild(copy);
  }
  body.appendChild(content); body.appendChild(actions);
  el.appendChild(body);
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
  return el;
}
// 把助手消息流式渲染进 el，并按当前 DOM 同步历史到后端
async function streamPaper(el) {
  syncPaperHistoryFromDOM();
  const hist = state.paperHistory.slice();
  const message = hist.length ? hist[hist.length - 1].content : "";
  const history = hist.slice(0, -1); // 排除当前这条提问（后端会单独附加 message）
  const contentEl = el.querySelector(".pm-content");
  let html = "";
  try {
    const resp = await fetch("/api/paper/chat/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paper_id: state.paperId, message, history, language: $("#language").value }),
    });
    if (!resp.ok) throw new Error("请求失败：" + resp.status);
    await consumeSSE(resp.body, (ev, data) => {
      if (ev === "paper_delta") { html += data.delta; contentEl.innerHTML = renderMarkdown(html); $("#paperMessages").scrollTop = $("#paperMessages").scrollHeight; }
      else if (ev === "error") toast(data.message, true);
    });
    el._text = html;
    syncPaperHistoryFromDOM();
    logPaperHistory();
    renderRightRail();
  } catch (e) {
    toast(e.message, true);
    if (!html) contentEl.textContent = "生成失败：" + e.message;
    el._text = html;
  }
  // 完整生成（或失败）后再显示复制 / 重新生成按钮
  const a = el.querySelector(".pm-actions");
  if (a) { a.style.display = "flex"; delete a.dataset.pending; }
  const mbody = el.querySelector(".pm-body");
  if (mbody) mbody.style.paddingBottom = "";
}
async function paperSend() {
  const msg = $("#paperInput").value.trim();
  if (!msg) return;
  if (!state.paperId) return toast("请先上传论文", true);
  appendPaperMsg("user", msg);
  $("#paperInput").value = "";
  const el = appendPaperMsg("assistant", "");
  // 对话一开始就写入「最近动态」（右侧栏）
  syncPaperHistoryFromDOM();
  logPaperHistory();
  renderRightRail();
  await streamPaper(el);
}
async function regeneratePaper(el) {
  if (!state.paperId) return toast("请先上传论文", true);
  const box = $("#paperMessages");
  const next = el.nextSibling;
  el.remove();
  const newEl = appendPaperMsg("assistant", "");
  if (next && next.parentNode === box) box.insertBefore(newEl, next);
  else box.appendChild(newEl);
  await streamPaper(newEl);
}

function logPaperHistory() {
  if (!state.paperId) return;
  fetch("/api/paper/history", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      paper_id: state.paperId,
      filename: $("#paperTitle").textContent.replace(/（.*）$/, ""),
      transcript: state.paperHistory,
    }),
  }).catch(() => {});
}

// 思路提炼：把整段对话收敛成「提炼指南」（思考框架，非成稿）
function syncAdvisorHistoryFromDOM() {
  const hist = [];
  $$("#advisorMessages .advisor-msg").forEach((m) => {
    const role = m.dataset.role, text = m._text || "";
    if (role && text) hist.push({ role, content: text });
  });
  state.advisorHistory = hist;
}
function appendAdvisorMsg(role, text) {
  const box = $("#advisorMessages");
  const empty = box.querySelector(".empty"); if (empty) empty.remove();
  const el = document.createElement("div");
  el.className = "advisor-msg " + role;
  el.dataset.role = role;
  el._text = text || "";
  const body = document.createElement("div");
  body.className = "advisor-body";
  const content = document.createElement("div");
  content.className = "advisor-content";
  content.innerHTML = text ? renderMarkdown(text) : "";
  const actions = document.createElement("div");
  actions.className = "advisor-actions";
  if (role === "user") {
    const edit = document.createElement("button");
    edit.className = "advisor-btn advisor-edit"; edit.textContent = "✎ 修改";
    edit.addEventListener("click", () => { $("#advisorInput").value = el._text; $("#advisorInput").focus(); });
    actions.appendChild(edit);
  } else {
    actions.style.display = "none";
    actions.dataset.pending = "1";
    body.style.paddingBottom = "14px";
    const regen = document.createElement("button");
    regen.className = "advisor-btn advisor-regen"; regen.textContent = "↻ 重新生成";
    regen.addEventListener("click", () => regenerateAdvisor(el));
    const copy = document.createElement("button");
    copy.className = "advisor-btn advisor-copy"; copy.textContent = "复制";
    copy.addEventListener("click", () => copyText(el._text, copy));
    actions.appendChild(regen); actions.appendChild(copy);
  }
  body.appendChild(content); body.appendChild(actions);
  el.appendChild(body);
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
  return el;
}
function eviLog(msg) {
  const log = document.getElementById("advisorEvidenceLog");
  if (!log) return;
  const d = document.createElement("div");
  d.className = "evi-step"; d.textContent = msg;
  log.appendChild(d); log.scrollTop = log.scrollHeight;
}

async function streamAdvisor(el) {
  syncAdvisorHistoryFromDOM();
  const hist = state.advisorHistory.slice();
  const message = hist.length ? hist[hist.length - 1].content : "";
  const history = hist.slice(0, -1);
  const contentEl = el.querySelector(".advisor-content");
  let html = "";
  el._choices = null;       // 本轮教练抛出的选择题
  el._needEvidence = null;  // 本轮教练判断需要自主检索证据的原因
  // 检索状态条：向用户明确展示『正在检索真实文献』，体现专业性
  const advStatus = $("#advisorStatus");
  const setAdvStatus = (text, done) => {
    if (!advStatus) return;
    advStatus.hidden = false;
    advStatus.classList.toggle("done", !!done);
    advStatus.innerHTML = `<span class="spin"></span><span>${text}</span>`;
  };
  if (advStatus) advStatus.hidden = true;

  // 检索 / 思考阶段的「不断 flush 省略号」动画：从请求发出到正式回答前，
  // 让回复气泡里始终有生长的点点点，体现过程在进行（含等待模型决定检索式、网络检索 + LLM 过滤）。
  let _dotTimer = null, _dotN = 0, _dotLabel = "";
  const _renderRetriDots = () => {
    const dots = ".".repeat(_dotN % 4);  // 0→1→2→3 循环，形成 flush 效果
    contentEl.innerHTML =
      '<div class="retri-pending"><span class="spin"></span><span>' + _dotLabel + dots + "</span></div>";
    _dotN++;
  };
  const stopRetriDots = () => { if (_dotTimer) { clearInterval(_dotTimer); _dotTimer = null; } };
  const startRetriDots = (label) => {
    stopRetriDots();
    _dotLabel = label || "处理中…";
    _dotN = 0;
    _renderRetriDots();
    _dotTimer = setInterval(_renderRetriDots, 420);
  };
  try {
    const resp = await fetch("/api/advisor/chat/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history, language: $("#language").value }),
    });
    if (!resp.ok) throw new Error("请求失败：" + resp.status);
    startRetriDots("🤔 正在分析您的研究问题…");  // 请求即启动 loading 动画，避免气泡空白
    await consumeSSE(resp.body, (ev, data) => {
      if (ev === "advisor_delta") {
        stopRetriDots();                 // 停止检索省略号动画
        if (advStatus) advStatus.hidden = true;  // 开始生成回答，检索阶段结束
        html += data.delta; contentEl.innerHTML = renderMarkdown(html); $("#advisorMessages").scrollTop = $("#advisorMessages").scrollHeight;
      }
      else if (ev === "advisor_choices") { el._choices = data.questions || []; }
      else if (ev === "need_evidence") {
        el._needEvidence = data.reason || "";
        // 仅在【气泡内】显示「检索中」flush 动画；聊天框外的状态条/弹窗提示已移除，避免重复打扰
        startRetriDots("🔍 正在检索真实文献依据" + (data.reason ? "：" + data.reason : ""));
        $("#advisorEvidenceWin").classList.remove("collapsed");
        const log = $("#advisorEvidenceLog"); if (log) log.innerHTML = "";
      }
      else if (ev === "plan") {
        if (data.strategy) eviLog("🎯 检索策略：" + data.strategy);
        (data.queries || []).forEach((q, i) => eviLog("🔎 检索式 " + (i + 1) + "：" + q));
      }
      else if (ev === "step_done") { eviLog("✓ 检索到 " + (data.found || 0) + " 篇文献依据"); }
      else if (ev === "sources") {
        stopRetriDots();                 // 检索完成：刷新掉 flush 加载态
        window._advisorEvidence = data.sources;
        renderAdvisorEvidence(data.sources);
        setRightCite(data.sources);
        // 检索有结果后先「刷新」loading 提示，给一行过渡，随后由 advisor_delta 覆盖为正式回答
        contentEl.innerHTML = '<div class="retri-done">✓ 已检索 ' + (data.count || 0) + ' 篇真实文献，正在组织回答…</div>';
        eviLog("🎉 已检索 " + (data.count || 0) + " 篇，并同步到右侧「本次引用」");
      }
      else if (ev === "error") {
        stopRetriDots();
        if (advStatus) advStatus.hidden = true;
        // 错误直接在气泡内呈现，避免只弹 toast 被忽略、气泡却永远停在「正在组织回答…」
        contentEl.innerHTML =
          '<div class="retri-error">⚠️ 生成中断：' + esc(data.message || "未知错误，请重试") + '</div>';
        toast(data.message || "生成失败，请重试", true);
      }
    });
    if (html) contentEl.innerHTML = renderMarkdown(html);  // 兜底：确保最终回答已渲染到气泡
    el._text = html;
    syncAdvisorHistoryFromDOM();
    if (el._choices && el._choices.length) renderAdvisorChoices(el, el._choices);
  } catch (e) {
    stopRetriDots();
    toast(e.message, true);
    if (advStatus) advStatus.hidden = true;
    if (!html) contentEl.textContent = "生成失败：" + e.message;
    el._text = html;
  }
  const a = el.querySelector(".advisor-actions");
  if (a) { a.style.display = "flex"; delete a.dataset.pending; }
  const mbody = el.querySelector(".advisor-body");
  if (mbody) mbody.style.paddingBottom = "";
  saveAdvisorHistory();  // 每轮结束后沉淀到历史动态 / 最近动态，支持后续继续工作
}

// 把当前思路提炼对话保存进统一历史（同一会话更新一条，支持从历史点回继续）
function saveAdvisorHistory() {
  syncAdvisorHistoryFromDOM();
  if (!state.advisorHistory.length) return;
  if (!state.advisorId) state.advisorId = "adv-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
  const topic = (state.advisorHistory.find((h) => h.role === "user") || {}).content || "思路提炼";
  fetch("/api/advisor/history", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ advisor_id: state.advisorId, topic, transcript: state.advisorHistory }),
  }).then(() => { renderRightRail(); }).catch(() => {});
}

// 选择题交互：把教练抛出的选择题渲染为选项按钮 +「其他（自行输入）」，
// 选中后自动把文本填入输入框（不自动发送）。
function renderAdvisorChoices(el, questions) {
  const body = el.querySelector(".advisor-body");
  if (!body || !questions || !questions.length) return;
  const input = $("#advisorInput");
  const wrap = document.createElement("div");
  wrap.className = "advisor-choices";
  // 多个选择题共享同一个输入框，答案按题号累积，避免互相覆盖。
  const answers = {};                                  // qi -> 该题回答（整行文本）
  const qLabel = (q, qi) => q.question || ("问题 " + (qi + 1));
  const prefixOf = (q, qi) => `（针对「${qLabel(q, qi)}」）`;
  // 把用户在输入框里手动编辑过的各题答案先读回来（按前缀匹配整行），避免重建时丢失
  const readback = () => {
    const lines = input.value.split("\n");
    questions.forEach((q, qi) => {
      const pre = prefixOf(q, qi);
      const line = lines.find((l) => l.startsWith(pre));
      if (line != null) answers[qi] = line;
    });
  };
  // 依题号顺序把所有已答问题拼回输入框
  const rebuild = () => {
    const parts = [];
    questions.forEach((q, qi) => { if (answers[qi]) parts.push(answers[qi]); });
    input.value = parts.join("\n");
    input.focus();
    try { input.setSelectionRange(input.value.length, input.value.length); } catch (_) {}
  };
  questions.forEach((q, qi) => {
    const card = document.createElement("div");
    card.className = "choice-card";
    const qel = document.createElement("div");
    qel.className = "choice-q";
    qel.innerHTML = `<span class="choice-tag">请选择</span>${esc(qLabel(q, qi))}`;
    card.appendChild(qel);
    const opts = document.createElement("div");
    opts.className = "choice-opts";
    const fill = (label, isOther) => {
      readback();  // 先保住其它题已编辑的答案
      opts.querySelectorAll(".choice-chip").forEach((x) => x.classList.remove("active"));
      const prefix = prefixOf(q, qi);
      answers[qi] = isOther ? `${prefix}我的想法：` : `${prefix}我选：${label}`;
      rebuild();
    };
    (q.options || []).forEach((opt) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "choice-chip"; b.textContent = opt;
      b.addEventListener("click", () => { fill(opt, false); b.classList.add("active"); });
      opts.appendChild(b);
    });
    const other = document.createElement("button");
    other.type = "button"; other.className = "choice-chip choice-other";
    other.textContent = "✎ 其他（自行输入）";
    other.addEventListener("click", () => { fill("", true); other.classList.add("active"); });
    opts.appendChild(other);
    card.appendChild(opts);
    wrap.appendChild(card);
  });
  body.appendChild(wrap);
}

async function advisorSend() {
  const msg = $("#advisorInput").value.trim();
  if (!msg) return;
  appendAdvisorMsg("user", msg);
  $("#advisorInput").value = "";
  const el = appendAdvisorMsg("assistant", "");
  await streamAdvisor(el);
}
async function regenerateAdvisor(el) {
  const box = $("#advisorMessages");
  const next = el.nextSibling;
  el.remove();
  const newEl = appendAdvisorMsg("assistant", "");
  if (next && next.parentNode === box) box.insertBefore(newEl, next);
  else box.appendChild(newEl);
  await streamAdvisor(newEl);
}
function advisorNew() {
  state.advisorHistory = [];
  state.advisorId = null;  // 开启新会话，后续保存生成新的历史记录
  $("#advisorMessages").innerHTML = `<div class="empty">描述你的研究兴趣或卡点，例如：「我想做医疗 RAG 的上下文压缩，但不知道从哪个点切入。」</div>`;
  state.advisorGuideMd = "";
  $("#advisorGuideBody").innerHTML = `<div class="empty">在左侧对话中梳理思路后，点击「生成指南」导出一份结构化思路提炼结果。指南会按<strong>已锚定的研究要素</strong>与<strong>待论证的研究要素</strong>两组沉淀。</div>`;
  $("#advisorGuideActions").classList.add("hidden");
  // 复位检索依据子窗口
  state._autoEvidenceTopic = null;
  window.advisorEvidence = [];
  renderRightCitations();  // 新对话开始，清空右侧「本次引用」
  $("#advisorEvidenceLog").innerHTML = `<div class="empty">与专业相关的论断会<strong>先检索真实文献、再结合引用作答</strong>，检索过程与结果同步到右侧「本次引用」。</div>`;
  $("#advisorEvidenceList").innerHTML = "";
  $("#advisorEvidenceWin").classList.remove("collapsed");
}
function copyAdvisorChat() {
  const text = state.advisorHistory
    .map((h) => (h.role === "user" ? "我：" : "Hy3：") + "\n" + h.content)
    .join("\n\n");
  copyText(text, $("#advisorCopyBtn"));
}
async function generateAdvisorGuide() {
  syncAdvisorHistoryFromDOM();
  if (!state.advisorHistory.length) return toast("先和教练聊几句再生成指南", true);
  const btn = $("#advisorGuideBtn");
  btn.disabled = true; btn.textContent = "生成中…";
  $("#advisorGuideBody").innerHTML = `<div class="empty">正在基于对话生成提炼指南…</div>`;
  try {
    const resp = await fetch("/api/advisor/guide", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ history: state.advisorHistory, language: $("#language").value }),
    });
    if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || ("请求失败：" + resp.status)); }
    const data = await resp.json();
    renderAdvisorGuide(data);
    toast("提炼指南已生成");
  } catch (e) {
    toast(e.message, true);
    $("#advisorGuideBody").innerHTML = `<div class="empty">生成失败：${e.message}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = "生成指南";
  }
}
function renderAdvisorGuide(data) {
  const confirmed = data.confirmed || [];
  const pending = data.pending || [];
  let md = `# ${data.title || "提炼指南"}\n`;
  if (data.summary) md += `\n> ${data.summary}\n`;
  md += "\n## 已锚定的研究要素\n\n";
  for (const s of confirmed) md += `### ${s.title}\n\n${s.body || ""}\n\n`;
  md += "## 待论证的研究要素\n\n";
  for (const s of pending) md += `### ${s.title}\n\n${s.body || ""}\n\n`;
  state.advisorGuideMd = md;
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const groupHtml = (title, items, cls) => {
    if (!items.length) return "";
    const secs = items.map((s) =>
      `<div class="guide-sec"><div class="guide-sec-title">${esc(s.title)}</div><div class="guide-sec-body">${renderMarkdown(s.body || "")}</div></div>`
    ).join("");
    return `<div class="guide-group ${cls}">
      <div class="guide-group-head" data-toggle-group="${cls}">
        <span class="gg-dot"></span><span class="gg-title">${esc(title)}</span>
        <span class="gg-count">${items.length}</span><span class="gg-chevron">▾</span>
      </div>
      <div class="guide-group-body">${secs}</div>
    </div>`;
  };
  const html =
    `<div class="guide-doc">` +
    `<div class="guide-title">${esc(data.title || "提炼指南")}</div>` +
    (data.summary ? `<div class="guide-summary">${esc(data.summary)}</div>` : "") +
    groupHtml("已锚定的研究要素", confirmed, "confirmed") +
    groupHtml("待论证的研究要素", pending, "pending") +
    `</div>`;
  $("#advisorGuideBody").innerHTML = html;
  $("#advisorGuideActions").classList.remove("hidden");
  // 分组折叠交互
  $$("#advisorGuideBody .guide-group-head").forEach((h) =>
    h.addEventListener("click", () => h.closest(".guide-group").classList.toggle("collapsed")));
}

function renderAdvisorEvidence(sources) {
  const box = $("#advisorEvidenceList");
  if (!box) return;
  // 多轮对话：每轮检索到的文献按 source_id 追加，已存在则跳过，不整体刷新覆盖
  for (const s of (sources || [])) {
    const sid = s.source_id || "";
    if (box.querySelector("#evi-" + sid.replace(/[^a-zA-Z0-9_-]/g, ""))) continue;
    const card = document.createElement("div");
    card.className = "evi-card";
    card.id = "evi-" + sid;
    card.innerHTML = `
      <div class="evi-title"><span class="src-id">[${sid}]</span>
        ${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>` : esc(s.title)}</div>
      <div class="evi-meta">${esc((s.authors || []).slice(0, 4).join(", "))}${s.year ? " · " + s.year : ""}${s.venue ? " · " + esc(s.venue) : ""}</div>
      <div class="evi-abs">${esc((s.abstract || s.snippet || "").slice(0, 220))}</div>`;
    box.appendChild(card);
  }
}
// 右侧「本次引用」：随当前页面切换，只展示该页面对应的引用结果。
// - research 页：本次深度研究的报告引用（state.sources）
// - search 页（智能检索）：本次智能检索报告的引用（window._smartCited）
// - advisor 页：本次思路提炼检索到的文献依据（window.advisorEvidence）
// - 其它页面：无引用
function renderRightCitations() {
  const box = $("#rrCite"), sub = $("#rrCiteSub");
  let items = [];
  if (currentView === "research") {
    items = Object.values(state.sources || {});
  } else if (currentView === "search") {
    items = (state.searchMode === "smart") ? (window._smartCited || window._smartSources || []) : [];
  } else if (currentView === "advisor") {
    items = (window.advisorEvidence || []);
  }
  if (!Array.isArray(items) || !items.length) {
    box.innerHTML = `<div class="rr-empty">当前页面暂无引用。在「深度研究 / 智能检索 / 思路提炼」中检索文献后，本次引用会随页面切换显示对应结果。</div>`;
    sub.textContent = "";
    return;
  }
  sub.textContent = items.length + " 篇";
  box.innerHTML = items.map((s) => {
    const url = s.url || "";
    const sid = s.source_id || "";
    const title = s.title || sid;
    return `<div class="rr-cite-item" data-sid="${esc(sid)}">
      <span class="rr-cite-id">${esc(sid)}</span>
      <div class="rr-cite-txt">
        <div class="rr-cite-title">${esc(trunc(title, 28))}</div>
        ${url ? `<a class="rr-cite-link" href="${esc(url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">🔗 溯源</a>` : ""}
      </div>
    </div>`;
  }).join("");
  box.querySelectorAll(".rr-cite-item").forEach((el) => {
    if (currentView === "search") el.addEventListener("click", () => gotoSmartSource(el.dataset.sid));
  });
}

// 把思路提炼检索到的文献依据写入「本次引用」（按当前页切换展示）
function setRightCite(sources) {
  const incoming = Array.isArray(sources) ? sources : [];
  const existing = Array.isArray(window.advisorEvidence) ? window.advisorEvidence : [];
  // 思路提炼多轮对话：每轮检索到的文献按 source_id 去重【追加】，而非整体刷新覆盖
  const seen = new Set(existing.map((s) => s.source_id));
  for (const s of incoming) {
    if (s && s.source_id && !seen.has(s.source_id)) {
      existing.push(s);
      seen.add(s.source_id);
    }
  }
  window.advisorEvidence = existing;
  const box = $("#rrCite");
  const prevTop = box ? box.scrollTop : 0;
  renderRightCitations();
  if (box) box.scrollTop = prevTop;  // 追加时保留滚动位置，避免跳动
}

// 从文库选择一篇含正文的 PDF 发起研讨
async function openPaperLibPicker() {
  const box = $("#paperLibList");
  if (!box) return;
  box.innerHTML = `<div class="empty">加载文库…</div>`;
  openFlowModal("从文库选择论文", $("#paperLibPicker"));
  try {
    const r = await fetch("/api/library");
    const d = await r.json();
    const items = (d.items || []).filter((it) => (it.text || "").trim().length >= 200);
    if (!items.length) {
      box.innerHTML = `<div class="empty">文库中没有可用于研讨的 PDF 正文。请先在「我的文库」上传 PDF。</div>`;
      return;
    }
    box.innerHTML = items.map((it) => `
      <button class="lib-pick" data-id="${esc(it.saved_id)}">
        <span class="lp-title">${esc(it.title)}</span>
        <span class="lp-meta">${esc(typeLabel(it.source_type) || "文档")} · ${(it.text || "").length} 字</span>
      </button>`).join("");
    box.querySelectorAll(".lib-pick").forEach((b) => b.addEventListener("click", () => {
      paperFromLibrary(b.dataset.id); closeFlowModal();
    }));
  } catch (e) { box.innerHTML = `<div class="empty">加载失败</div>`; }
}
async function paperFromLibrary(saved_id) {
  try {
    const r = await fetch("/api/paper/from-library", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ saved_id }),
    });
    if (!r.ok) throw new Error((await r.json()).detail || "加载失败");
    const d = await r.json();
    state.paperId = d.paper_id; state.paperHistory = [];
    $("#paperTitle").textContent = d.filename + (d.trunc_note ? " " + d.trunc_note : "");
    $("#paperEmpty").classList.add("hidden");
    $("#paperChat").classList.remove("hidden");
    $("#paperMessages").innerHTML = `<div class="empty">论文已就绪，开始提问吧。</div>`;
    toast(`已载入文库论文 ${d.filename}（${d.chars} 字）`);
    renderRightRail();
  } catch (e) { toast(e.message, true); }
}

// 从历史页恢复论文研讨会话（论文仍在内存时有效）
function openPaperHistory(h) {
  switchView("paper");
  state.paperId = h.paper_id;
  state.paperHistory = (h.transcript || []).slice();
  $("#paperTitle").textContent = (h.title || h.filename || "论文") + "（历史会话）";
  $("#paperSetup").classList.add("hidden");
  $("#paperChat").classList.remove("hidden");
  const box = $("#paperMessages");
  box.innerHTML = "";
  if (state.paperHistory.length) {
    state.paperHistory.forEach((turn) => appendPaperMsg(turn.role, turn.content));
  } else {
    box.innerHTML = `<div class="empty">暂无历史对话，向论文提问吧。</div>`;
  }
  toast("已恢复论文研讨会话（若论文已过期需重新上传）");
  renderRightRail();
}

// ---------- 创造工坊 · AI Feature Studio (New) ----------
const FEATURE_CATEGORIES = [
  ["Research", "科研"], ["Medical", "医学"], ["Education", "教育"], ["Writing", "写作"],
  ["Coding", "编程"], ["Office", "办公"], ["Translation", "翻译"], ["Data Analysis", "数据分析"],
  ["Knowledge Management", "知识管理"], ["Others", "其他"],
];
const CAT_LABEL = Object.fromEntries(FEATURE_CATEGORIES);
let vbPlacedComponents = [];

function switchForgeScope(scope) {
  state.featureScope = scope;
  $$("#forgeSubtabs .forge-tab").forEach((x) => x.classList.toggle("active", x.dataset.scope === scope));
  ["marketplace", "mine", "favorites", "templates", "creator"].forEach((s) => {
    const el = $("#forgeContent" + s.charAt(0).toUpperCase() + s.slice(1));
    if (el) el.classList.toggle("hidden", s !== scope);
  });
  if (scope === "creator") {
    renderCreatorDashboard();
  } else {
    loadFeatures($("#featSearch").value.trim());
  }
  const labels = {
    marketplace: "🔥 精选功能",
    mine: "📦 我的功能",
    favorites: "⭐ 我的收藏",
    templates: "📋 官方模板"
  };
  const label = $("#forgeListLabel");
  if (label && labels[scope]) label.textContent = labels[scope];
}

async function loadFeatures(q) {
  const scope = state.featureScope || "marketplace";
  const category = state.featureCategory || "All";
  const sort = $("#forgeSort")?.value || "popular";
  let allFeatures = [];
  try {
    let url = "/api/features?scope=" + encodeURIComponent(scope === "marketplace" ? "discover" : scope);
    if (q) url += "&q=" + encodeURIComponent(q);
    if (category && category !== "All") url += "&category=" + encodeURIComponent(category);
    const r = await fetch(url);
    const d = await r.json();
    allFeatures = d.features || [];
  } catch (e) { allFeatures = []; toast("加载功能失败", true); }
  try {
    const rf = await fetch("/api/features/favorites");
    const df = await rf.json();
    state.featureFavs = df.features || [];
    const favIds = new Set(state.featureFavs.map((f) => f.id));
    allFeatures.forEach((f) => f.favorited = favIds.has(f.id));
  } catch (e) { state.featureFavs = []; }

  if (sort === "newest") allFeatures.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  else if (sort === "rating") allFeatures.sort((a, b) => (b.rating || 0) - (a.rating || 0));
  else if (sort === "forks") allFeatures.sort((a, b) => (b.forks || 0) - (a.forks || 0));
  else allFeatures.sort((a, b) => (b.use_count || 0) - (a.use_count || 0));

  state.featureList = allFeatures;
  updateForgeStats(allFeatures);
  renderFeatCats();

  const lists = {
    marketplace: "#featList",
    mine: "#myFeatList",
    favorites: "#favFeatList",
    templates: "#tplFeatList"
  };
  Object.entries(lists).forEach(([s, sel]) => {
    const box = $(sel);
    if (!box) return;
    let list = allFeatures;
    if (s === "mine") list = allFeatures.filter((f) => f.creator === "user");
    else if (s === "favorites") list = allFeatures.filter((f) => f.favorited);
    else if (s === "templates") list = allFeatures.filter((f) => f.is_template);
    renderFeatGrid(box, list, s);
  });
}

function updateForgeStats(features) {
  const creators = new Set(features.map((f) => f.creator)).size;
  const forks = features.reduce((s, f) => s + (f.forks || 0), 0);
  const uses = features.reduce((s, f) => s + (f.use_count || 0), 0);
  animateNum("forgeStatFeatures", features.length);
  animateNum("forgeStatCreators", creators);
  animateNum("forgeStatForks", forks);
  animateNum("forgeStatUses", uses);
}

function animateNum(id, target) {
  const el = $("#" + id);
  if (!el) return;
  const start = parseInt(el.textContent) || 0;
  const duration = 800;
  const startTime = performance.now();
  function step(now) {
    const p = Math.min((now - startTime) / duration, 1);
    const val = Math.round(start + (target - start) * (1 - Math.pow(1 - p, 3)));
    el.textContent = val;
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function renderFeatCats() {
  const box = $("#forgeCats");
  if (!box) return;
  const cur = state.featureCategory || "All";
  const chips = [["All", "全部"]].concat(FEATURE_CATEGORIES)
    .map(([k, lbl]) => `<button class="forge-cat ${k === cur ? "active" : ""}" data-cat="${k}">${lbl}</button>`)
    .join("");
  box.innerHTML = chips;
  box.querySelectorAll(".forge-cat").forEach((b) =>
    b.addEventListener("click", () => {
      state.featureCategory = b.dataset.cat;
      renderFeatCats();
      loadFeatures($("#featSearch").value.trim());
    }));
}

function featCardHTML(f) {
  const isFav = f.favorited;
  const isMine = f.creator === "user";
  const badges = [];
  if (f.is_template) badges.push(`<span class="feat-badge official">官方</span>`);
  if (f.verified) badges.push(`<span class="feat-badge verified">认证</span>`);
  if ((f.use_count || 0) > 50) badges.push(`<span class="feat-badge trending">🔥 热门</span>`);
  const rating = f.rating_count ? f.rating.toFixed(1) : "0.0";
  const stars = renderStars(f.rating || 0);
  const catClass = (f.category || "Others").replace(/\s+/g, "");
  return `
    <div class="feat-card" data-id="${f.id}">
      <div class="feat-card-cover ${esc(catClass)}">
        <span class="feat-cover-cat">${esc(CAT_LABEL[f.category] || f.category || "其他")}</span>
      </div>
      <div class="feat-card-body">
        <div class="feat-top">
          <div class="feat-emoji">${esc(f.emoji || "🧩")}</div>
          <div class="feat-head">
            <div class="feat-name">${esc(f.name)}<div class="feat-badges">${badges.join("")}</div></div>
          </div>
        </div>
        <div class="feat-desc">${esc(f.description || "")}</div>
        <div class="feat-tags">${(f.tags || []).slice(0, 3).map((t) => `<span class="feat-tag">${esc(t)}</span>`).join("")}</div>
        <div class="feat-meta">
          <span class="feat-rating">${stars} <span style="color:#f7c948">${rating}</span> <span class="feat-rating-count">(${f.rating_count || 0})</span></span>
          <div class="feat-stats-mini">
            <span class="feat-stat-mini" title="使用次数">👥 ${f.use_count || 0}</span>
            <span class="feat-stat-mini" title="Fork 次数">⑂ ${f.forks || 0}</span>
          </div>
        </div>
        <div class="feat-actions">
          <button class="btn-primary feat-open-btn" data-id="${f.id}">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            打开
          </button>
          <button class="feat-icon-btn ${isFav ? "favorited" : ""}" data-id="${f.id}" data-action="fav" title="${isFav ? "取消收藏" : "收藏"}">${isFav ? "★" : "☆"}</button>
          <button class="feat-icon-btn" data-id="${f.id}" data-action="fork" title="Fork">⑂</button>
          ${isMine ? `<button class="feat-icon-btn" data-id="${f.id}" data-action="edit" title="编辑">✎</button>` : ""}
          ${isMine ? `<button class="feat-icon-btn" data-id="${f.id}" data-action="delete" title="删除">🗑</button>` : ""}
        </div>
      </div>
    </div>`;
}

function renderStars(rating) {
  const full = Math.floor(rating);
  let s = "";
  for (let i = 1; i <= 5; i++) s += i <= full ? "★" : "☆";
  return s;
}

function renderFeatGrid(box, list, scope) {
  const emptyMsgs = {
    marketplace: "没有匹配的功能，换个关键词或分类，或点击「新建功能」创建自己的。",
    mine: "还没有创建功能，点击「新建功能」开始吧。",
    favorites: "还没有收藏的功能，点击卡片上的 ☆ 收藏功能。",
    templates: "暂无官方模板。"
  };
  if (!list || !list.length) {
    box.innerHTML = `<div class="empty">${emptyMsgs[scope] || "暂无功能"}</div>`;
    return;
  }
  box.innerHTML = list.map((f) => featCardHTML(f)).join("");
  bindFeatCards(box);
}

function bindFeatCards(scope) {
  scope.querySelectorAll(".feat-card").forEach((card) => {
    const id = card.dataset.id;
    card.addEventListener("click", (e) => {
      if (e.target.closest(".feat-icon-btn")) return;
      if (fwState.feature && fwState.feature.id === id) return;
      e.preventDefault();
      if (location.hash === "#/feature/" + id) {
        enterFeatureWorkspace(id);
      } else {
        window.location.hash = "#/feature/" + id;
      }
    });
  });
  scope.querySelectorAll(".feat-open-btn").forEach((b) =>
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      const id = b.dataset.id;
      if (fwState.feature && fwState.feature.id === id) return;
      window.location.hash = "#/feature/" + id;
    }));
  scope.querySelectorAll(".feat-icon-btn").forEach((b) => {
    const action = b.dataset.action;
    const id = b.dataset.id;
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      if (action === "fav") featureToggleFav(id);
      else if (action === "fork") featureFork(id);
      else if (action === "edit") editFeature(id);
      else if (action === "delete") featureDelete(id);
    });
  });
}

async function featureToggleFav(id) {
  try {
    const r = await fetch("/api/features/favorite", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const d = await r.json();
    const upd = (arr) => (arr || []).forEach((f) => { if (f.id === id) f.favorited = d.favorited; });
    upd(state.featureList); upd(state.featureFavs);
    loadFeatures($("#featSearch").value.trim());
  } catch (e) { toast("操作失败", true); }
}

async function featureFork(id) {
  try {
    const r = await fetch("/api/features/" + id + "/fork", { method: "POST" });
    const d = await r.json();
    if (!d.feature) throw new Error("Fork 失败");
    toast("已 Fork 为「我的」功能：" + d.feature.name);
    switchForgeScope("mine");
    await loadFeatures("");
  } catch (e) { toast(e.message || "Fork 失败", true); }
}

async function featureDelete(id) {
  if (!confirm("确定删除该功能？此操作不可撤销。")) return;
  try {
    await fetch("/api/features/" + id, { method: "DELETE" });
    state.featureList = state.featureList.filter((f) => f.id !== id);
    state.featureFavs = state.featureFavs.filter((f) => f.id !== id);
    loadFeatures($("#featSearch").value.trim());
    toast("已删除");
  } catch (e) { toast("删除失败", true); }
}

function renderCreatorDashboard() {
  const myFeatures = (state.featureList || []).filter((f) => f.creator === "user");
  const totalUses = myFeatures.reduce((s, f) => s + (f.use_count || 0), 0);
  const totalFavs = (state.featureFavs || []).length;
  const totalForks = myFeatures.reduce((s, f) => s + (f.forks || 0), 0);
  const avgRating = myFeatures.length ? (myFeatures.reduce((s, f) => s + (f.rating || 0), 0) / myFeatures.length).toFixed(1) : "0.0";

  animateNum("cmWorks", myFeatures.length);
  animateNum("cmUsers", totalUses);
  animateNum("cmFavs", totalFavs);
  animateNum("cmForks", totalForks);
  const cmRating = $("#cmRating");
  if (cmRating) cmRating.textContent = avgRating;

  const worksBox = $("#creatorWorks");
  if (!myFeatures.length) {
    worksBox.innerHTML = `<div class="empty">创建功能后这里会显示作品数据。</div>`;
  } else {
    worksBox.innerHTML = myFeatures.map((f) => `
      <div class="creator-work-item">
        <div class="feat-emoji">${esc(f.emoji || "🧩")}</div>
        <div class="cw-info">
          <div class="cw-name">${esc(f.name)}</div>
          <div class="cw-meta">v${esc(f.version || "1.0.0")} · ${fmtTsShort(f.updated_at || f.created_at)}</div>
        </div>
        <div class="cw-stats">
          <span class="cw-stat">👥 ${f.use_count || 0}</span>
          <span class="cw-stat">★ ${f.favorite_count || 0}</span>
          <span class="cw-stat">⑂ ${f.forks || 0}</span>
          <span class="cw-stat">${renderStars(f.rating || 0)} ${(f.rating || 0).toFixed(1)}</span>
        </div>
      </div>`).join("");
  }
}

// 打开一个"完全独立"的功能：按设计级别渲染不同内部结构的界面
async function openFeature(id, standalone) {
  let f = [...state.featureList, ...state.featureFavs].find((x) => x.id === id);
  if (!f) {
    try {
      const r = await fetch("/api/features/" + id);
      const d = await r.json();
      if (d.feature) f = d.feature;
    } catch (e) {}
  }
  if (!f) { toast("功能不存在", true); return; }
  state.featureChatId = id;
  state.featureHistory = [];
  state.featureStandalone = !!standalone;
  const isBuilder = f.design_level === "builder" || (f.ui && f.ui.type === "builder");
  state.featureMode = isBuilder ? "builder" : "simple";
  state.featureBlocks = isBuilder && f.ui && f.ui.layout ? f.ui.layout : [];
  const isMine = f.creator === "user";
  const catLbl = CAT_LABEL[f.category] || f.category || "其他";
  $("#featureModalTitle").innerHTML =
    `${esc(f.emoji || "🧩")} <span>${esc(f.name)}</span>` +
    `<span class="feat-lv">${isBuilder ? "拖拽设计" : "一句话"}</span>`;
  const head =
    `<div class="feat-head-card">` +
      `<div class="feat-emoji lg">${esc(f.emoji || "🧩")}</div>` +
      `<div class="feat-head-info">` +
        `<div class="feat-name">${esc(f.name)}</div>` +
        `<div class="feat-desc">${esc(f.description || "")}</div>` +
        `<div class="feat-tags">${(f.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>` +
        `<div class="feat-meta">` +
          `<span class="feat-cat">🏷 ${catLbl}</span>` +
          `<span class="feat-ver">v${esc(f.version || "1.0.0")}</span>` +
          `<span class="feat-use">👥 使用 ${f.use_count || 0}</span>` +
          `<span class="feat-rate">★ ${f.rating_count ? f.rating.toFixed(1) + " (" + f.rating_count + ")" : "暂无评分"}</span>` +
        `</div>` +
        `<div class="feat-modal-actions">` +
          renderRateEdit(f) +
          `<button class="feat-fork-btn btn-soft" data-id="${f.id}">⑂ Fork 复用</button>` +
          (isMine ? `<button class="feat-edit-btn btn-soft" data-id="${f.id}">✎ 编辑</button>` : "") +
        `</div>` +
      `</div></div>`;
  const body = $("#featureModalBody");
  if (isBuilder) {
    body.innerHTML = head +
      `<div id="featureBlocks" class="feature-blocks"></div>` +
      `<div id="featureMessages" class="feature-messages"></div>` +
      `<div class="feature-input-row">` +
        `<textarea id="featureInput" class="feature-input" rows="2" placeholder="补充提问或说明…"></textarea>` +
        `<button id="featureSend" class="btn-primary">运行</button>` +
      `</div>`;
    renderBuilderBlocks(f);
  } else {
    body.innerHTML = head +
      `<div id="featureMessages" class="feature-messages"></div>` +
      `<div class="feature-input-row">` +
        `<textarea id="featureInput" class="feature-input" rows="2" placeholder="向该功能提问…"></textarea>` +
        `<button id="featureSend" class="btn-primary">发送</button>` +
      `</div>`;
    if (f.starters && f.starters.length) {
      const bar = document.createElement("div");
      bar.className = "feat-starters";
      bar.innerHTML = f.starters.map((s) => `<button class="chip" data-q="${esc(s)}">${esc(s)}</button>`).join("");
      $("#featureMessages").before(bar);
      bar.querySelectorAll(".chip").forEach((b) =>
        b.addEventListener("click", () => { $("#featureInput").value = b.dataset.q; featureSend(); }));
    }
  }
  $("#featureMessages").innerHTML = `<div class="empty">已载入功能「${esc(f.name)}」。开始向它提问吧。</div>`;
  $("#featureInput").value = "";
  // 独立工作空间（方案 §8）：隐藏左侧导航，整页作为该功能的专属界面
  if (state.featureStandalone) {
    document.body.classList.add("feature-standalone");
    $("#featureModal").classList.add("standalone");
  } else {
    document.body.classList.remove("feature-standalone");
    $("#featureModal").classList.remove("standalone");
  }
  $("#featureModal").classList.remove("hidden");
  $("#featureInput").focus();
  $("#featureSend").addEventListener("click", featureSend);
  $("#featureInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); featureSend(); }
  });
  body.querySelector(".feat-fork-btn")?.addEventListener("click", () => featureFork(f.id));
  body.querySelector(".feat-edit-btn")?.addEventListener("click", () => editFeature(f.id));
  bindRateEdit(body, f);
}

// 评分星星（可点击）
function renderRateEdit(f) {
  const cur = Math.round(f.rating || 0);
  let s = `<span class="feat-rate-edit" title="点击为这个功能评分">`;
  for (let i = 1; i <= 5; i++) s += `<span class="rstar ${i <= cur ? "on" : ""}" data-stars="${i}">★</span>`;
  return s + `</span>`;
}
function bindRateEdit(scope, f) {
  scope.querySelectorAll(".rstar").forEach((st) =>
    st.addEventListener("click", () => featureRate(f.id, +st.dataset.stars)));
}
async function featureRate(fid, stars) {
  try {
    const r = await fetch("/api/features/" + fid + "/rate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stars }),
    });
    const d = await r.json();
    if (!d.feature) throw new Error("评分失败");
    toast("感谢评分：" + stars + "★");
    const upd = (arr) => (arr || []).forEach((x) => {
      if (x.id === fid) { x.rating = d.feature.rating; x.rating_count = d.feature.rating_count; }
    });
    upd(state.featureList); upd(state.featureFavs);
  } catch (e) { toast("评分失败", true); }
}

// 渲染「初步设计」级别的模块（输入/下拉/对话/结果）
function renderBuilderBlocks(f) {
  const wrap = $("#featureBlocks");
  wrap.innerHTML = "";
  (f.ui.layout || []).forEach((b) => {
    const el = document.createElement("div");
    el.className = "fb-block fb-" + b.type;
    let inner = `<div class="fb-block-label">${esc(b.label || b.type)}</div>`;
    if (b.type === "input")
      inner += `<input id="fb_${b.key}" class="lit-input" placeholder="${esc(b.placeholder || "")}" />`;
    else if (b.type === "textarea")
      inner += `<textarea id="fb_${b.key}" class="query-input" rows="3" placeholder="${esc(b.placeholder || "")}"></textarea>`;
    else if (b.type === "select")
      inner += `<select id="fb_${b.key}" class="lit-select">${(b.options || []).map((o) => `<option>${esc(o)}</option>`).join("")}</select>`;
    else if (b.type === "chat")
      inner += `<div class="fb-chat-note">↳ 下方对话区</div>`;
    else if (b.type === "output")
      inner += `<div id="fb_${b.key}" class="fb-output"><div class="out-body">结果将显示在这里</div><button class="copy-btn copy-float" type="button" data-copy="#fb_${b.key} .out-body">复制</button></div>`;
    el.innerHTML = inner;
    wrap.appendChild(el);
  });
}
function appendFeatureMsg(role, text) {
  const box = $("#featureMessages");
  const empty = box.querySelector(".empty"); if (empty) empty.remove();
  const el = document.createElement("div");
  el.className = "paper-msg " + role;
  el.innerHTML = `<div class="pm-body">${text ? renderMarkdown(text) : ""}</div>`;
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
  return el;
}
async function featureSend() {
  const msg0 = $("#featureInput").value.trim();
  if (!msg0 || !state.featureChatId) return;
  // 初步设计级别：把表单字段 + 补充输入拼成一个完整消息
  let composed = msg0;
  if (state.featureMode === "builder") {
    const parts = [];
    (state.featureBlocks || []).forEach((b) => {
      if (["input", "textarea", "select"].includes(b.type)) {
        const v = ($("#fb_" + b.key)?.value || "").trim();
        if (v) parts.push(`${b.label || b.key}：${v}`);
      }
    });
    if (parts.length) composed = parts.join("\n") + (msg0 ? "\n\n补充：" + msg0 : "");
  }
  appendFeatureMsg("user", composed);
  $("#featureInput").value = "";
  const history = state.featureHistory.slice();
  state.featureHistory.push({ role: "user", content: composed });
  const el = appendFeatureMsg("assistant", "");
  const bodyEl = el.querySelector(".pm-body");
  let html = "";
  try {
    const resp = await fetch("/api/features/" + state.featureChatId + "/chat/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: composed, history, language: $("#language").value }),
    });
    if (!resp.ok) throw new Error("请求失败：" + resp.status);
    await consumeSSE(resp.body, (ev, data) => {
      if (ev === "feat_delta") { html += data.delta; bodyEl.innerHTML = renderMarkdown(html); $("#featureMessages").scrollTop = $("#featureMessages").scrollHeight; }
      else if (ev === "error") toast(data.message, true);
      else if (ev === "done") {
        state.featureHistory.push({ role: "assistant", content: html });
        if (state.featureMode === "builder") {
          const out = $("#fb_output");
          if (out) { const ob = out.querySelector(".out-body"); if (ob) ob.innerHTML = renderMarkdown(html); }
        }
      }
    });
  } catch (e) { toast(e.message, true); if (!html) bodyEl.textContent = "生成失败：" + e.message; }
}

// 新建功能：三种创建模式
function openNewFeature() {
  state._nfPreview = null;
  state._nfEditId = null;
  state._nfLevel = "quick";
  state._nfChat = [];
  state._nfDesign = null;
  vbPlacedComponents = [];
  $("#nfDesc").value = "";
  $("#qbCategory").value = "";
  $("#nfPreview").classList.add("hidden");
  $("#nfPreview").innerHTML = "";
  $("#qbProgress").classList.add("hidden");
  $("#nfChat").innerHTML = `<div class="empty">描述你的功能，AI 会理解场景并推荐组件布局。例如：「我要做一个论文审稿工具，需要上传PDF、显示证据面板、输出审稿意见」</div>`;
  $("#nfChatInput").value = "";
  $("#nfBuilder").classList.add("hidden");
  $("#nfBuilder").innerHTML = "";
  state._nfChat = [];
  switchBuilderMode("quick");
  initVisualBuilderDragDrop();
  $("#newFeatureModal").classList.remove("hidden");
  setTimeout(() => $("#nfDesc").focus(), 100);
}

function switchBuilderMode(level) {
  state._nfLevel = level;
  $$("#builderModeSelect .builder-mode-card").forEach((c) => c.classList.toggle("active", c.dataset.level === level));
  $$(".builder-panel").forEach((p) => p.classList.toggle("active", p.dataset.level === level));
}

function initVisualBuilderDragDrop() {
  const canvas = $("#vbCanvas");
  if (!canvas || canvas._inited) return;
  canvas._inited = true;
  $$(".vb-comp").forEach((comp) => {
    comp.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("compType", comp.dataset.comp);
      e.dataTransfer.effectAllowed = "copy";
    });
  });
  canvas.addEventListener("dragover", (e) => {
    e.preventDefault();
    canvas.classList.add("drag-over");
  });
  canvas.addEventListener("dragleave", () => canvas.classList.remove("drag-over"));
  canvas.addEventListener("drop", (e) => {
    e.preventDefault();
    canvas.classList.remove("drag-over");
    const compType = e.dataTransfer.getData("compType");
    if (!compType) return;
    addVBComponent(compType);
  });
}

const VB_COMP_INFO = {
  input: { icon: "📝", name: "Input" }, upload: { icon: "📎", name: "Upload" },
  button: { icon: "🔘", name: "Button" }, pdf: { icon: "📄", name: "PDF" },
  markdown: { icon: "📑", name: "Markdown" }, chart: { icon: "📊", name: "Chart" },
  table: { icon: "📋", name: "Table" }, timeline: { icon: "⏱️", name: "Timeline" },
  mindmap: { icon: "🧠", name: "MindMap" }, search: { icon: "🔍", name: "Search" },
  code: { icon: "⌨️", name: "Code" }, image: { icon: "🖼️", name: "Image" }
};

function addVBComponent(type) {
  const info = VB_COMP_INFO[type] || { icon: "🧩", name: type };
  vbPlacedComponents.push({ type, ...info });
  renderVBCanvas();
  updateVBSuggest(type);
}

function removeVBComponent(idx) {
  vbPlacedComponents.splice(idx, 1);
  renderVBCanvas();
}

function renderVBCanvas() {
  const canvas = $("#vbCanvas");
  const empty = canvas.querySelector(".vb-canvas-empty");
  if (!vbPlacedComponents.length) {
    if (empty) empty.style.display = "flex";
    canvas.querySelectorAll(".vb-placed-comp").forEach((el) => el.remove());
    return;
  }
  if (empty) empty.style.display = "none";
  canvas.innerHTML = `<div class="vb-canvas-empty"><div class="vb-empty-icon">🎯</div><div class="vb-empty-text">从左侧拖拽组件开始设计</div></div>`;
  vbPlacedComponents.forEach((c, i) => {
    const el = document.createElement("div");
    el.className = "vb-placed-comp";
    el.innerHTML = `<span class="vb-pc-icon">${c.icon}</span><span class="vb-pc-name">${c.name}</span><button class="vb-pc-del" data-idx="${i}">✕</button>`;
    canvas.appendChild(el);
  });
  canvas.querySelectorAll(".vb-pc-del").forEach((b) =>
    b.addEventListener("click", () => removeVBComponent(+b.dataset.idx)));
}

function updateVBSuggest(type) {
  const suggestions = {
    pdf: "检测到 PDF 组件，推荐添加：Evidence Panel（证据面板）、Citation（引用）、Outline（大纲）",
    table: "检测到 Data Table，推荐添加：Statistics Chart（统计图表）",
    input: "可以添加 Button 和 Output 组件来形成完整交互",
    upload: "上传组件建议搭配 Markdown 或 Table 来展示结果",
    chart: "Chart 组件可与 Table 配合展示数据分析结果"
  };
  const suggest = suggestions[type] || "继续添加组件，AI 会根据你的组合推荐最佳布局";
  const sugBox = $("#vbSuggest");
  if (sugBox) sugBox.querySelector(".vb-suggest-text").textContent = suggest;
}

// 编辑已有功能（我的）：复用高级设计代码模板预填，保存走 PUT 更新
async function editFeature(id) {
  let f = [...state.featureList, ...state.featureFavs].find((x) => x.id === id);
  if (!f) {
    try { const r = await fetch("/api/features/" + id); const d = await r.json(); f = d.feature; } catch (e) {}
  }
  if (!f) { toast("功能不存在", true); return; }
  openNewFeature();
  state._nfEditId = id;
  switchBuilderMode("quick");
  $("#nfDesc").value = f.description || f.prompt || "";
  if (f.category) $("#qbCategory").value = f.category;
  const m = $("#nfPreview");
  m.classList.remove("hidden");
  m.innerHTML = `
    <div class="nf-card">
      <div class="nf-card-head"><span class="nf-emoji">${esc(f.emoji || "🧩")}</span>
        <span class="nf-name">${esc(f.name)}</span>
        <span class="feat-lv">编辑中</span></div>
      <div class="nf-desc">${esc(f.description || "")}</div>
      <div class="nf-tags">${(f.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>
      <div class="nf-prompt-label">系统提示词</div>
      <pre class="nf-prompt">${esc(f.prompt || "")}</pre>
      ${f.starters && f.starters.length ? `<div class="nf-prompt-label">示例提问</div><div class="nf-tags">${f.starters.map((s) => `<span class="tag">${esc(s)}</span>`).join("")}</div>` : ""}
      <div class="nf-preview-actions">
        <button id="nfSaveEdit" class="btn-primary">保存修改</button>
      </div>
    </div>`;
  $("#nfSaveEdit").addEventListener("click", () => saveEditFeature(id));
  $("#newFeatureModal").classList.remove("hidden");
}

async function saveEditFeature(id) {
  const desc = $("#nfDesc").value.trim();
  try {
    const r = await fetch("/api/features/" + id, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: desc }),
    });
    if (!r.ok) throw new Error("保存失败");
    toast("修改已保存");
    $("#newFeatureModal").classList.add("hidden");
    loadFeatures($("#featSearch").value.trim());
  } catch (e) { toast(e.message, true); }
}

// ---- 一句话（简单）级别 ----
async function generateFeature() {
  const desc = $("#nfDesc").value.trim();
  if (!desc) return toast("请先描述你想要的功能", true);
  const box = $("#nfPreview");
  box.classList.remove("hidden");
  box.innerHTML = `<p class="nf-loading">Hy3 正在设计功能…</p>`;
  try {
    const r = await fetch("/api/features/generate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: desc, language: $("#language").value }),
    });
    const d = await r.json();
    const f = d.feature || {};
    state._nfPreview = f;
    box.innerHTML = `
      <div class="nf-card">
        <div class="nf-card-head"><span class="nf-emoji">${esc(f.emoji || "🧩")}</span>
          <span class="nf-name">${esc(f.name)}</span>
          <span class="feat-lv">一句话</span></div>
        <div class="nf-desc">${esc(f.description || "")}</div>
        <div class="nf-tags">${(f.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>
        <div class="nf-prompt-label">系统提示词</div>
        <pre class="nf-prompt">${esc(f.prompt || "")}</pre>
        ${f.starters && f.starters.length ? `<div class="nf-prompt-label">示例提问</div><div class="nf-tags">${f.starters.map((s) => `<span class="tag">${esc(s)}</span>`).join("")}</div>` : ""}
        <div class="nf-preview-actions">
          <button id="nfSave" class="btn-primary">保存到创造工坊</button>
          <button id="nfRegenerate" class="btn-soft">重新生成</button>
        </div>
      </div>`;
    $("#nfSave").addEventListener("click", saveFeature);
    $("#nfRegenerate").addEventListener("click", generateFeature);
  } catch (e) { box.innerHTML = `<p class="nf-loading">生成失败：${esc(e.message)}</p>`; }
}
async function saveFeature() {
  const f = state._nfPreview;
  if (!f) return;
  try {
    const r = await fetch("/api/features", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...f, design_level: f.design_level || "simple", creator: "user" }),
    });
    if (!r.ok) throw new Error("保存失败");
    toast("功能已保存");
    $("#newFeatureModal").classList.add("hidden");
    loadFeatures($("#featSearch").value.trim());
  } catch (e) { toast(e.message, true); }
}

// ---- 初步设计（拖拽）级别 ----
async function nfDesignSend() {
  const v = $("#nfChatInput").value.trim();
  if (!v) return;
  state._nfChat.push({ role: "user", content: v });
  $("#nfChatInput").value = "";
  renderNfChat();
  try {
    const r = await fetch("/api/features/design/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ history: state._nfChat, language: $("#language").value }),
    });
    const d = await r.json();
    state._nfChat.push({ role: "assistant", content: d.reply || "" });
    renderNfChat();
  } catch (e) { toast("设计对话失败", true); }
}
function renderNfChat() {
  const box = $("#nfChat");
  if (!state._nfChat.length) { box.innerHTML = `<div class="empty">和右侧设计助手聊聊你的功能想法吧。</div>`; return; }
  box.innerHTML = state._nfChat.map((m) =>
    `<div class="nf-msg ${m.role === "user" ? "user" : "bot"}">${esc(m.content)}</div>`).join("");
  box.scrollTop = box.scrollHeight;
}
async function nfBuild() {
  const box = $("#nfBuilder");
  const transcript = state._nfChat.map((m) => `${m.role === "user" ? "用户" : "助手"}：${m.content}`).join("\n");
  box.classList.remove("hidden");
  box.innerHTML = `<p class="nf-loading">正在生成可拖拽页面…</p>`;
  try {
    const r = await fetch("/api/features/build", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript, language: $("#language").value }),
    });
    const d = await r.json();
    state._nfDesign = d.feature || {};
    state._nfDesignLayout = (state._nfDesign.ui && state._nfDesign.ui.layout) || [];
    renderNfBuilder();
  } catch (e) { box.innerHTML = `<p class="nf-loading">生成失败：${esc(e.message)}</p>`; }
}
function renderNfBuilder() {
  const box = $("#nfBuilder");
  const f = state._nfDesign;
  box.innerHTML = `
    <div class="nf-card">
      <div class="nf-card-head"><span class="nf-emoji">${esc(f.emoji || "🧩")}</span>
        <span class="nf-name">${esc(f.name)}</span>
        <span class="feat-lv">拖拽设计</span></div>
      <div class="nf-desc">${esc(f.description || "")}</div>
      <div class="nf-tags">${(f.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>
      <div class="nf-prompt-label">可拖拽模块（上下拖动调整顺序，逻辑已确定）</div>
      <div id="nfBlocks" class="nf-blocks"></div>
      <div class="nf-preview-actions">
        <button id="nfSaveBuilder" class="btn-primary">保存到创造工坊</button>
        <button id="nfRebuild" class="btn-soft">重新生成</button>
      </div>
    </div>`;
  const blk = $("#nfBlocks");
  state._nfDesignLayout.forEach((b, i) => {
    const el = document.createElement("div");
    el.className = "nf-block"; el.draggable = true; el.dataset.i = i;
    el.innerHTML = `<span class="nf-grip">⠿</span><span class="nf-block-label">${esc(b.label || b.type)}</span><span class="nf-block-type">${esc(b.type)}</span>`;
    blk.appendChild(el);
  });
  bindNfDrag(blk);
  $("#nfSaveBuilder").addEventListener("click", saveBuilderFeature);
  $("#nfRebuild").addEventListener("click", nfBuild);
}
function bindNfDrag(container) {
  let dragEl = null;
  container.addEventListener("dragstart", (e) => {
    dragEl = e.target.closest(".nf-block");
    e.dataTransfer.effectAllowed = "move";
  });
  container.addEventListener("dragover", (e) => {
    e.preventDefault();
    const after = getDragAfter(container, e.clientY);
    if (!dragEl) return;
    if (after == null) container.appendChild(dragEl);
    else container.insertBefore(dragEl, after);
  });
  container.addEventListener("dragend", () => {
    const order = [...container.querySelectorAll(".nf-block")].map((el) => state._nfDesignLayout[+el.dataset.i]);
    state._nfDesignLayout = order;
  });
}
function getDragAfter(container, y) {
  const els = [...container.querySelectorAll(".nf-block:not(.dragging)")];
  return els.reduce((closest, child) => {
    const box = child.getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0 && offset > closest.offset) return { offset, element: child };
    return closest;
  }, { offset: -Infinity, element: null }).element;
}
async function saveBuilderFeature() {
  const f = state._nfDesign;
  if (!f) return;
  try {
    const r = await fetch("/api/features", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: f.name, emoji: f.emoji, description: f.description, prompt: f.prompt,
        tags: f.tags || [], design_level: "builder", creator: "user",
        ui: { type: "builder", layout: state._nfDesignLayout },
      }),
    });
    if (!r.ok) throw new Error("保存失败");
    toast("功能已保存");
    $("#newFeatureModal").classList.add("hidden");
    loadFeatures($("#featSearch").value.trim());
  } catch (e) { toast(e.message, true); }
}

// ---- 高级设计（代码模板）级别 ----
function nfTemplate() {
  return JSON.stringify({
    name: "我的功能",
    emoji: "🧩",
    description: "一句话说明这个功能做什么",
    prompt: "你是一个专业助手，帮助用户……（给底层模型的系统提示词）",
    tags: ["自定义"],
    design_level: "simple",
    ui: { type: "chat" },
    starters: ["给我一个示例", "有什么注意事项？"],
  }, null, 2);
}
function nfCodeReset() {
  $("#nfCode").value = nfTemplate();
  const m = $("#nfCodeMsg"); m.textContent = ""; m.className = "nf-msg";
}
async function nfCodeSave() {
  const msg = $("#nfCodeMsg");
  let obj;
  if ($("#devName").value.trim()) {
    obj = {
      name: $("#devName").value.trim(),
      emoji: $("#devEmoji").value.trim() || "🧩",
      description: $("#devDesc").value.trim(),
      prompt: $("#devPrompt").value.trim(),
      tags: $("#devTags").value.split(",").map((t) => t.trim()).filter(Boolean),
      category: $("#devCategory").value || "Others",
    };
    let ui = null;
    try { if ($("#devUI").value.trim()) ui = JSON.parse($("#devUI").value); } catch (e) {}
    if (ui) obj.ui = ui;
    let wf = null;
    try { if ($("#devWorkflow").value.trim()) wf = JSON.parse($("#devWorkflow").value); } catch (e) {}
    if (wf) obj.workflow = wf;
    if (!obj.prompt) {
      try {
        const raw = $("#nfCode").value.trim();
        const codeObj = JSON.parse(raw);
        obj.prompt = codeObj.prompt || "";
        obj.starters = codeObj.starters || [];
        obj.design_level = codeObj.design_level || "simple";
      } catch (e) {}
    }
  } else {
    const raw = $("#nfCode").value.trim();
    try { obj = JSON.parse(raw); }
    catch (e) { msg.textContent = "JSON 解析失败：" + e.message; msg.className = "nf-msg err"; return; }
  }
  if (!obj.name || !obj.prompt) { msg.textContent = "缺少必填字段：名称 / Prompt"; msg.className = "nf-msg err"; return; }
  obj.creator = "user";
  if (!obj.design_level) obj.design_level = "simple";
  if (!obj.ui) obj.ui = { type: "chat" };
  try {
    let r;
    if (state._nfEditId) {
      r = await fetch("/api/features/" + state._nfEditId, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(obj),
      });
    } else {
      r = await fetch("/api/features", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(obj),
      });
    }
    if (!r.ok) throw new Error("保存失败");
    msg.textContent = "✓ 已保存"; msg.className = "nf-msg ok";
    setTimeout(() => $("#newFeatureModal").classList.add("hidden"), 600);
    loadFeatures($("#featSearch").value.trim());
  } catch (e) { msg.textContent = e.message; msg.className = "nf-msg err"; }
}

// ---------- 反馈看板 (Feedback board) ----------
async function loadFeedback() {
  try {
    const r = await fetch("/api/feedback");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    const upd = $("#fbCloudUpdated");
    if (upd) upd.textContent = d.updated_at ? `更新截至 ${fmtTsShort(d.updated_at)}` : "";
    state.feedbackItems = d.items || [];
    state.feedbackCloud = d.cloud || [];
    try { state._fbUpvoted = JSON.parse(localStorage.getItem("hy3-fb-upvoted") || "{}") || {}; } catch (e) { state._fbUpvoted = {}; }
    const cats = d.categories || ["功能建议", "缺陷报告", "性能与稳定", "交互与界面", "内容与质量", "检索与数据", "文档与帮助", "其他"];
    if (!cats.includes(state._fbCat)) state._fbCat = cats[0];
    renderFbCats(cats);
    const sortEl = $("#fbSort"); if (sortEl) sortEl.value = state._fbSort;
    renderFbList();
    drawWordCloud();
  } catch (e) { toast("加载反馈失败：" + (e && e.message ? e.message : e), true); }
}
function renderFbCats(cats) {
  const box = $("#fbCats");
  box.innerHTML = cats.map((c) =>
    `<button class="fb-cat ${c === state._fbCat ? "active" : ""}" data-cat="${esc(c)}">${esc(c)}</button>`).join("");
  box.querySelectorAll(".fb-cat").forEach((b) =>
    b.addEventListener("click", () => {
      state._fbCat = b.dataset.cat;
      box.querySelectorAll(".fb-cat").forEach((x) => x.classList.toggle("active", x === b));
    }));
}
function renderFbList() {
  const box = $("#fbList");
  let items = state.feedbackItems.slice();
  if (state._fbFilter) items = items.filter((it) => (it.keywords || []).includes(state._fbFilter));
  // 排序：up 最多 / 最新反馈
  if (state._fbSort === "up") {
    items.sort((a, b) => (b.upvotes || 0) - (a.upvotes || 0)
      || new Date(b.created_at) - new Date(a.created_at));
  } else {
    items.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  }
  $("#fbCount").textContent = items.length ? `（${items.length}）` : "";
  if (!items.length) { box.innerHTML = `<div class="empty">${state._fbFilter ? "没有包含该关键词的反馈。" : "暂无反馈，来做第一个吧。"}</div>`; return; }
  box.innerHTML = items.map((it) => {
    const voted = !!state._fbUpvoted[it.id];
    return `
    <div class="fb-card">
      <div class="fb-card-head">
        <span class="fb-badge c-${esc(it.category)}">${esc(it.category)}</span>
        <span class="fb-time">${fmtTs(it.created_at)}</span>
      </div>
      <div class="fb-content">${esc(it.content)}</div>
      <div class="fb-card-foot">
        <div class="fb-kw">${(it.keywords || []).map((k) =>
          `<button class="fb-kw-btn ${k === state._fbFilter ? "active" : ""}" data-k="${esc(k)}">${esc(k)}</button>`).join("")}</div>
        <button class="fb-up ${voted ? "voted" : ""}" data-up="${esc(it.id)}" title="${voted ? "取消 up" : "up 这条反馈"}">
          <span class="fb-up-ic">▲</span><span class="fb-up-txt">up</span><span class="fb-up-n">${it.upvotes || 0}</span>
        </button>
      </div>
    </div>`;
  }).join("");
  box.querySelectorAll(".fb-kw-btn").forEach((b) =>
    b.addEventListener("click", () => {
      state._fbFilter = b.dataset.k;
      $("#fbClearFilter").classList.remove("hidden");
      renderFbList();
    }));
  box.querySelectorAll(".fb-up").forEach((b) =>
    b.addEventListener("click", () => fbUpvote(b.dataset.up)));
}
async function fbUpvote(id) {
  const voted = !!state._fbUpvoted[id];
  const url = voted
    ? `/api/feedback/${encodeURIComponent(id)}/down`
    : `/api/feedback/${encodeURIComponent(id)}/up`;
  try {
    const r = await fetch(url, { method: "POST" });
    if (!r.ok) throw new Error("操作失败");
    const d = await r.json();
    const it = state.feedbackItems.find((x) => x.id === id);
    if (it) it.upvotes = d.upvotes;
    if (voted) delete state._fbUpvoted[id];
    else state._fbUpvoted[id] = true;
    try { localStorage.setItem("hy3-fb-upvoted", JSON.stringify(state._fbUpvoted)); } catch (e) {}
    renderFbList();
  } catch (e) { toast(e.message, true); }
}
async function fbSubmit() {
  const content = $("#fbContent").value.trim();
  if (!content) return toast("请先填写反馈内容", true);
  try {
    const r = await fetch("/api/feedback", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category: state._fbCat, content, language: $("#language").value }),
    });
    if (!r.ok) throw new Error((await r.json()).detail || "提交失败");
    const d = await r.json();
    $("#fbContent").value = "";
    $("#fbMasked").classList.toggle("hidden", !d.item.masked);
    if (d.item.masked) setTimeout(() => $("#fbMasked").classList.add("hidden"), 3000);
    toast("感谢反馈！");
    loadFeedback();
  } catch (e) { toast(e.message, true); }
}

// 词云：自包含 canvas 螺旋布局（悬停看次数，点击筛选）
// 按真实显示尺寸 × devicePixelRatio 渲染，保证清晰且不变形。
function drawWordCloud() {
  const canvas = $("#fbCloud");
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth, H = canvas.clientHeight;
  if (!W || !H) return;                 // 视图隐藏时尺寸为 0，等 ResizeObserver 触发
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);   // 之后均以 CSS 像素绘制
  ctx.clearRect(0, 0, W, H);
  const words = (state.feedbackCloud || []).slice().sort((a, b) => b.count - a.count);
  const empty = $("#fbCloudEmpty");
  if (!words.length) { empty.classList.remove("hidden"); state._cloudBoxes = []; return; }
  empty.classList.add("hidden");
  const boxes = [];
  const palette = ["#6ea8fe", "#7ee0c0", "#f6c177", "#f78fb3", "#a0a8ff", "#82d2a0", "#e0a3ff", "#ffb4a2"];
  const baseFont = 14, maxFont = 46;
  const rxScale = W / Math.max(1, H);   // 椭圆螺旋：横向随宽高比拉伸，铺满左右
  words.forEach((w, idx) => {
    const fontSize = Math.round(baseFont + (maxFont - baseFont) * Math.max(0, Math.min(1, (w.weight - 0.5) * 2)));
    ctx.font = `700 ${fontSize}px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif`;
    const tw = ctx.measureText(w.text).width, th = fontSize;
    for (let attempt = 0; attempt < 2000; attempt++) {
      const angle = attempt * 0.5;
      const radius = 5 * Math.sqrt(attempt);
      const x = W / 2 + radius * rxScale * Math.cos(angle) - tw / 2;
      const y = H / 2 + radius * Math.sin(angle) + th / 2;
      const box = { x: x - 6, y: y - th - 6, w: tw + 12, h: th + 12 };
      if (box.x < 0 || box.y < 0 || box.x + box.w > W || box.y + box.h > H) continue;
      if (boxes.some((p) => p.x < box.x + box.w && p.x + p.w > box.x && p.y < box.y + box.h && p.y + p.h > box.y)) continue;
      boxes.push({ ...box, text: w.text, count: w.count, ups: w.ups || 0 });
      ctx.fillStyle = palette[idx % palette.length];
      ctx.fillText(w.text, x, y);
      break;
    }
  });
  state._cloudBoxes = boxes;
}
function fbCloudHit(e) {
  const c = $("#fbCloud");
  const rect = c.getBoundingClientRect();
  const mx = (e.clientX - rect.left) * (c.clientWidth / rect.width);
  const my = (e.clientY - rect.top) * (c.clientHeight / rect.height);
  return (state._cloudBoxes || []).find((b) => mx >= b.x && mx <= b.x + b.w && my >= b.y && my <= b.y + b.h);
}

// 词云面板：八向拖拽缩放（上/下/左/右/四角），用 transform 平移避免挤动布局
function initCloudResizer() {
  const wrap = document.querySelector(".fb-cloud-wrap");
  const canvas = $("#fbCloud");
  if (!wrap || !canvas) return;
  ["n", "s", "e", "w", "ne", "nw", "se", "sw"].forEach((dir) => {
    const h = document.createElement("div");
    h.className = "cloud-rsz cloud-rsz-" + dir;
    h.dataset.dir = dir;
    wrap.appendChild(h);
  });
  let drag = null;
  wrap.querySelectorAll(".cloud-rsz").forEach((h) => {
    h.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      const r = wrap.getBoundingClientRect();
      drag = { dir: h.dataset.dir, sx: e.clientX, sy: e.clientY,
               w: r.width, h: r.height, tw: parseFloat(wrap.dataset.tx || 0), th: parseFloat(wrap.dataset.ty || 0) };
      h.setPointerCapture(e.pointerId);
      document.body.style.userSelect = "none";
    });
    h.addEventListener("pointermove", (e) => {
      if (!drag || drag.dir !== h.dataset.dir) return;
      const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
      let nw = drag.w, nh = drag.h, tx = drag.tw, ty = drag.th;
      if (drag.dir.includes("e")) nw = Math.max(320, drag.w + dx);
      if (drag.dir.includes("s")) nh = Math.max(200, drag.h + dy);
      if (drag.dir.includes("w")) { nw = Math.max(320, drag.w - dx); tx = drag.tw + (drag.w - nw); }
      if (drag.dir.includes("n")) { nh = Math.max(200, drag.h - dy); ty = drag.th + (drag.h - nh); }
      wrap.style.width = nw + "px";
      wrap.style.height = nh + "px";
      wrap.style.transform = `translate(${tx}px, ${ty}px)`;
      wrap.dataset.tx = tx; wrap.dataset.ty = ty;
    });
    const end = (e) => { if (drag && drag.dir === h.dataset.dir) { drag = null; document.body.style.userSelect = ""; } try { h.releasePointerCapture(e.pointerId); } catch (_) {} };
    h.addEventListener("pointerup", end);
    h.addEventListener("pointercancel", end);
  });
  // 尺寸变化（拖拽缩放 / 窗口缩放 / 视图切换显隐）自动重绘词云
  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => drawWordCloud());
    ro.observe(canvas);
  }
}

// ---------- helpers ----------
function switchTab(tab) {
  $$("#researchWorkspace .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
  $$("#researchWorkspace .tab-pane").forEach((p) => p.classList.toggle("active", p.id === "tab-" + tab));
}
function setMetric(id, val) { const el = $("#" + id); if (el && val != null && val !== "") el.textContent = val; }
function log(msg) { const d = document.createElement("div"); d.className = "line"; d.textContent = msg; $("#log").prepend(d); }
function toast(msg, err) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast" + (err ? " err" : "");
  clearTimeout(t._t); t._t = setTimeout(() => t.classList.add("hidden"), 3000);
}
function citeChip(sid) { return `<a class="cite" onclick="jumpSource('${sid}')">${sid}</a>`; }

// 查找引用来源（智能检索来源优先，其次研究来源）
function getSource(sid) {
  if (Array.isArray(window._smartSources)) {
    const s = window._smartSources.find((x) => x.source_id === sid);
    if (s) return s;
  }
  return state.sources[sid] || null;
}

// 点击引用：跳转到生成结果中对应的引用详情，并弹出溯源信息（含 URL）
function jumpSource(sid) {
  const el = document.getElementById("src-" + sid);
  const src = getSource(sid);
  if (el) {
    const tab = el.closest(".tab-pane");
    if (tab && !tab.classList.contains("active")) switchTab(tab.id.replace("tab-", ""));
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.style.borderColor = "var(--accent)";
    setTimeout(() => (el.style.borderColor = ""), 1600);
  } else if (src && Array.isArray(window._smartSources) && window._smartSources.indexOf(src) >= 0) {
    gotoSmartSource(sid);
    return;
  }
  showCitePop(sid);
}
window.jumpSource = jumpSource;

// 切到检索视图的「智能检索」面板并定位到对应来源
function gotoSmartSource(sid) {
  if (sid && String(sid).startsWith("r")) {
    // 思路提炼检索到的依据：直接在本视图内展开检索依据并溯源，不打断当前上下文
    switchView("advisor");
    const win = document.getElementById("advisorEvidenceWin");
    if (win) win.classList.remove("collapsed");
    setTimeout(() => {
      const el = document.getElementById("evi-" + sid);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.style.borderColor = "var(--accent)";
        setTimeout(() => (el.style.borderColor = ""), 1600);
      }
      showCitePop(sid);
    }, 60);
    return;
  }
  switchView("search");
  switchSearchMode("smart");
  setTimeout(() => {
    const el = document.getElementById("src-" + sid);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.style.borderColor = "var(--accent)";
      setTimeout(() => (el.style.borderColor = ""), 1600);
    }
    showCitePop(sid);
  }, 60);
}
window.gotoSmartSource = gotoSmartSource;

// 引用详情弹层：展示标题/作者/摘要，并提供可点击的溯源 URL
function showCitePop(sid) {
  const src = getSource(sid);
  $("#citePopTitle").textContent = "引用 " + sid;
  if (!src) {
    $("#citePopBody").innerHTML = `<div class="cp-meta">未找到该引用的详情（可能来自已切换的会话）。</div>`;
  } else {
    const url = src.url || "";
    $("#citePopBody").innerHTML = `
      <div class="cp-title">${esc(src.title)}</div>
      <div class="cp-meta">${esc((src.authors || []).slice(0, 5).join(", "))}${src.year ? " · " + src.year : ""}${src.venue ? " · " + esc(src.venue) : ""}</div>
      <div class="cp-abs">${esc((src.abstract || src.snippet || "").slice(0, 400))}</div>
      ${url
        ? `<a class="cp-link" href="${esc(url)}" target="_blank" rel="noopener">🔗 点击溯源（打开原始来源）</a>`
        : `<div class="cp-meta">（该来源未提供可点击链接）</div>`}
    `;
  }
  $("#citePop").classList.remove("hidden");
}
window.showCitePop = showCitePop;

// 把智能检索报告中的引用回填到右侧栏（点击可跳转 / 溯源）
function renderRightCite(reportMd) {
  const sids = [...new Set((reportMd.match(/\[s\d+\]/g) || []).map((x) => x.slice(1, -1)))];
  window._smartCited = sids.length
    ? (window._smartSources || []).filter((s) => sids.includes(s.source_id))
    : (window._smartSources || []);
  renderRightCitations();
}
function typeLabel(t) { return { paper: "论文", web: "网页", upload: "上传", note: "笔记" }[t] || t; }
function trunc(s, n) { return s.length > n ? s.slice(0, n) + "…" : s; }
function esc(s) { return (s || "").replace(/[&<>"]/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c])); }

// ---------- 复制增强：所有生成内容可复制（表格/代码单一复制 + .md 导出）----------
async function copyToClipboard(text) {
  text = String(text || "");
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_) { /* fall through */ }
  try {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.top = "-9999px"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.focus(); ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch (_) { return false; }
}

// 把 DOM 表格转回 Markdown（供"单一复制"使用）
function tableToMarkdown(table) {
  const rows = [...table.querySelectorAll("tr")];
  return rows.map((tr, ri) => {
    const cells = [...tr.querySelectorAll("th,td")].map((c) =>
      (c.textContent || "").trim().replace(/\|/g, "\\|").replace(/\s+/g, " "));
    const line = "| " + cells.join(" | ") + " |";
    if (ri === 0) {
      const sep = "| " + cells.map(() => "---").join(" | ") + " |";
      return line + "\n" + sep;
    }
    return line;
  }).join("\n");
}

// 复制容器全文：去掉所有"复制"按钮后再取纯文本
async function copyNode(container) {
  if (!container) return;
  const clone = container.cloneNode(true);
  clone.querySelectorAll(".copy-btn").forEach((b) => b.remove());
  const txt = (clone.innerText || clone.textContent || "").trim();
  if (!txt) return toast("内容为空，无可复制内容", true);
  const ok = await copyToClipboard(txt);
  toast(ok ? "已复制全文到剪贴板" : "复制失败，请手动选择", true);
}

function flashCopyBtn(btn, ok) {
  const old = btn.textContent;
  btn.textContent = ok ? "已复制 ✓" : "复制失败";
  btn.classList.add(ok ? "copied" : "copy-fail");
  setTimeout(() => { btn.textContent = old; btn.classList.remove("copied", "copy-fail"); }, 1300);
}

// 通过 MutationObserver 给所有"代码块"与"表格"自动挂上单一复制按钮
function initCopyEnhance() {
  const enhance = (node) => {
    if (!node || node.nodeType !== 1) return;
    // 代码块：用 .code-block 包裹并加复制按钮
    if (node.matches("pre.md-code") && !node.dataset.copyReady) {
      node.dataset.copyReady = "1";
      const wrap = document.createElement("div");
      wrap.className = "code-block";
      node.parentNode.insertBefore(wrap, node);
      wrap.appendChild(node);
      const btn = document.createElement("button");
      btn.type = "button"; btn.className = "copy-btn"; btn.textContent = "复制";
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const txt = node.querySelector("code")?.textContent || node.textContent;
        flashCopyBtn(btn, await copyToClipboard(txt));
      });
      wrap.appendChild(btn);
    }
    // 表格：在 .md-table-wrap 上加复制按钮（复制为 Markdown）
    if (node.matches(".md-table-wrap") && !node.dataset.copyReady) {
      node.dataset.copyReady = "1";
      const btn = document.createElement("button");
      btn.type = "button"; btn.className = "copy-btn"; btn.textContent = "复制";
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const tbl = node.querySelector("table");
        const txt = tbl ? tableToMarkdown(tbl) : node.innerText;
        flashCopyBtn(btn, await copyToClipboard(txt));
      });
      node.appendChild(btn);
    }
    node.querySelectorAll("pre.md-code, .md-table-wrap").forEach((c) => {
      if (!c.dataset.copyReady) enhance(c);
    });
  };
  const observer = new MutationObserver((muts) => {
    muts.forEach((m) => m.addedNodes.forEach((n) => {
      if (n.nodeType === 1) {
        if (n.matches && n.matches("pre.md-code, .md-table-wrap")) enhance(n);
        if (n.querySelectorAll) enhance(n);
      }
    }));
  });
  observer.observe(document.body, { childList: true, subtree: true });
  enhance(document.body);
  // 创造工坊输出区"复制"按钮（浮层式，data-copy 指向目标节点）
  document.addEventListener("click", (e) => {
    const fb = e.target.closest && e.target.closest(".copy-float");
    if (fb) {
      e.stopPropagation();
      const target = fb.dataset.copy ? $(fb.dataset.copy) : null;
      if (target) { flashCopyBtn(fb, true); copyNode(target); }
    }
  });
}

// 智能检索：复制为 Markdown（原始 md）/ 复制全文
async function onSmartCopyMd() {
  const md = state.smartReportMd || "";
  if (!md.trim()) return toast("暂无可复制的 Markdown（请先生成检索报告）", true);
  const ok = await copyToClipboard(md);
  toast(ok ? "已复制 Markdown 到剪贴板" : "复制失败，请手动选择", true);
}

// 把已渲染的报告导出为独立的 .html 文件（即把 Markdown 渲染结果固化成 HTML）
function downloadHtml(container, filename) {
  if (!container || !container.innerHTML.trim()) return toast("暂无可导出的内容（请先生成检索报告）", true);
  const clone = container.cloneNode(true);
  clone.querySelectorAll(".copy-btn").forEach((b) => b.remove());
  const body = clone.innerHTML;
  const css = `
    :root { color-scheme: light; }
    body { font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      max-width: 880px; margin: 32px auto; padding: 0 20px; color: #1f2430; line-height: 1.75; background: #fff; }
    .smart-report h1, .smart-report h2, .smart-report h3, .smart-report h4 { color: #1f2430; line-height: 1.4; margin: 20px 0 10px; }
    .smart-report h1 { font-size: 24px; border-bottom: 2px solid #d8dee4; padding-bottom: 8px; }
    .smart-report h2 { font-size: 19px; border-left: 4px solid #4c8bf5; padding-left: 10px; }
    .smart-report h3 { font-size: 16.5px; }
    .smart-report h4 { font-size: 14.5px; color: #5b6573; }
    .smart-report p { margin: 9px 0; }
    .smart-report ul { padding-left: 22px; } .smart-report li { margin: 4px 0; }
    .smart-report code.md-code { background: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 5px; padding: 1px 6px; font-size: 13px; }
    .smart-report pre.md-code { background: #f6f8fa; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 14px; overflow-x: auto; }
    .smart-report blockquote { margin: 12px 0; padding: 8px 14px; border-left: 4px solid #4c8bf5; background: #f3f6fb; border-radius: 0 8px 8px 0; color: #4a5568; }
    .smart-report hr { border: none; border-top: 1px solid #d8dee4; margin: 18px 0; }
    .smart-report .md-table-wrap { width: 100%; overflow-x: auto; margin: 10px 0 14px; }
    .smart-report table.md-table { border-collapse: collapse; width: 100%; min-width: 520px; font-size: 13.5px; }
    .smart-report table.md-table th, .smart-report table.md-table td { border: 1px solid #d8dee4; padding: 8px 11px; vertical-align: top; }
    .smart-report table.md-table th { background: #f0f4fa; font-weight: 700; white-space: nowrap; }
    .smart-report table.md-table tbody tr:nth-child(even) { background: #f7f9fc; }
    .smart-report a.cite { background: #e8f0ff; color: #2b6fd6; border-radius: 5px; padding: 0 5px; font-size: 12px; font-weight: 600; text-decoration: none; }
    .math-fallback { color: #b05; }
  `;
  const doc = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">`
    + `<meta name="viewport" content="width=device-width, initial-scale=1">`
    + `<title>${esc(filename)}</title><style>${css}</style></head>`
    + `<body><div class="smart-report">${body}</div></body></html>`;
  const blob = new Blob([doc], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
  toast("已下载 HTML 文件（Markdown 已渲染为 HTML）");
}
function downloadText(text, filename) {
  if (!text || !text.trim()) return toast("暂无可导出的内容", true);
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
  toast("已下载 Markdown 文件");
}

// minimal markdown -> html with [sN] citation chips, math (KaTeX) and code
function renderMath(tex, display) {
  if (window.katex) {
    try {
      return window.katex.renderToString(tex.trim(), { displayMode: !!display, throwOnError: false });
    } catch (e) { /* fall through */ }
  }
  const d = display ? "$$" : "$";
  return `<span class="math-fallback">${d}${esc(tex)}${d}</span>`;
}

// 行内渲染：在一段/一行内就地处理 公式 / 行内代码 / 引用 / 加粗，
// 保证行内公式不会把句子切断成多行（修复"莫名其妙的换行"）。
const _TK = "@@TK";  // 占位符前缀（普通文本中几乎不可能出现）
function renderInline(text) {
  const tokens = [];
  let s = text;
  // 1) 先抽取 行内公式/代码，避免被转义或误当 markdown
  s = s.replace(/\\\(([\s\S]+?)\\\)/g, (_, t) => { tokens.push(renderMath(t, false)); return _TK + (tokens.length - 1) + _TK; });
  s = s.replace(/\$([^$\n]+?)\$/g, (_, t) => { tokens.push(renderMath(t, false)); return _TK + (tokens.length - 1) + _TK; });
  s = s.replace(/`([^`\n]+)`/g, (_, t) => { tokens.push(`<code class="md-code">${esc(t)}</code>`); return _TK + (tokens.length - 1) + _TK; });
  // 2) 转义剩余文本
  s = esc(s);
  // 3) 引用 / 加粗
  s = s.replace(/\[(s\d+)\]/g, (_, sid) => `<a class="cite" onclick="jumpSource('${sid}')">${sid}</a>`);
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // 4) 还原占位符
  s = s.replace(new RegExp(_TK + "(\\d+)" + _TK, "g"), (_, i) => tokens[+i] ?? "");
  return s;
}

function unwrapCodeFence(md) {
  // 模型常把整份 Markdown 包进 ```markdown … ``` 代码块，导致标题/表格被原样当代码显示。
  // 这里把「包裹整段内容」的最外层围栏剥离掉，还原成真正的 Markdown。
  if (typeof md !== "string") return md;
  const t = md.trim();
  const m = t.match(/^```[^\n]*\n([\s\S]*?)\n?```$/);
  return m ? m[1] : md;
}

function renderMarkdown(md) {
  if (!md) return "";
  md = unwrapCodeFence(md);
  try {
    return renderMarkdownBody(md);
  } catch (e) {
    // 任何异常都不应让报告"渲染失败"：降级为转义纯文本
    return `<pre class="md-code">${esc(md)}</pre>`;
  }
}

function renderMarkdownBody(md) {
  const lines = md.split("\n");
  let html = "";
  let para = [];
  let inCode = false, codeBuf = "";
  let listOpen = false;
  const closeList = () => { if (listOpen) { html += "</ul>"; listOpen = false; } };
  const flushPara = () => {
    if (para.length) { html += "<p>" + para.map(renderInline).join("<br>") + "</p>"; para = []; }
  };
  // 表格检测：当前行像表格行，且下一行是分隔行（| --- | --- |）
  const looksTable = (l) =>
    /\|/.test(l) && !/^#{1,6}\s/.test(l) && !/^```/.test(l) &&
    !/^\s*[-*]\s/.test(l) && !/^\s*\d+\.\s/.test(l) && !/^[ \t]{0,3}>/.test(l);
  const isSepRow = (l) => {
    const t = l.trim().replace(/^\|/, "").replace(/\|$/, "");
    const cells = t.split("|").map((c) => c.trim());
    return cells.length >= 2 && cells.every((c) => /^:?-+:?$/.test(c));
  };
  const splitCells = (l) =>
    l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
  const alignOf = (c) => {
    const l = c.startsWith(":"), r = c.endsWith(":");
    if (l && r) return "center"; if (r) return "right"; if (l) return "left"; return "";
  };

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];
    // 围栏代码块 ```
    if (/^[ \t]*```/.test(line)) {
      if (!inCode) { flushPara(); closeList(); inCode = true; codeBuf = ""; }
      else { html += `<pre class="md-code"><code>${esc(codeBuf)}</code></pre>`; inCode = false; }
      continue;
    }
    if (inCode) { codeBuf += line + "\n"; continue; }

    // 块引用（连续 > 行合并为一段，Typora 风格）
    if (/^[ \t]{0,3}>/.test(line)) {
      const q = [];
      while (i < lines.length && /^[ \t]{0,3}>\s?(.*)$/.test(lines[i])) {
        const mq = lines[i].match(/^[ \t]{0,3}>\s?(.*)$/);
        q.push(mq[1]); i++;
      }
      i--; flushPara(); closeList();
      html += `<blockquote>${q.map(renderInline).join("<br>")}</blockquote>`;
      continue;
    }

    // 分隔线 ---
    if (/^[ \t]{0,3}(---|\*\*\*|___)\s*$/.test(line)) { flushPara(); closeList(); html += "<hr>"; continue; }

    // 表格（智能检索报告的核心交付物）：表头 + 分隔行 + 若干数据行
    if (looksTable(line) && i + 1 < lines.length && isSepRow(lines[i + 1])) {
      flushPara(); closeList();
      const headers = splitCells(line);
      const aligns = splitCells(lines[i + 1]).map(alignOf);
      const rows = [];
      let j = i + 2;
      while (j < lines.length && looksTable(lines[j])) {
        // 下一行若是分隔行则不属于数据行
        if (isSepRow(lines[j])) break;
        rows.push(splitCells(lines[j]));
        j++;
      }
      const th = headers.map((c, ci) =>
        `<th${aligns[ci] ? ` style="text-align:${aligns[ci]}"` : ""}>${renderInline(c)}</th>`).join("");
      const tb = rows.map((r) =>
        "<tr>" + r.map((c, ci) =>
          `<td${aligns[ci] ? ` style="text-align:${aligns[ci]}"` : ""}>${renderInline(c)}</td>`).join("") + "</tr>"
      ).join("");
      html += `<div class="md-table-wrap"><table class="md-table"><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table></div>`;
      i = j - 1; // 跳过已消费的表格行
      continue;
    }

    // 独占一行的块级公式 $$ ... $$ （仅在独占一行时块级渲染，避免行内公式被强制换行）
    const blkMath = line.match(/^\s*\$\$([\s\S]*)\$\$\s*$/);
    if (blkMath) { flushPara(); closeList(); html += renderMath(blkMath[1], true); continue; }

    // 标题（支持 1~6 级，允许行首最多 3 个空格缩进；尾部 # 关闭符也兼容）
    const h = line.match(/^[ \t]{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/);
    if (h) {
      flushPara(); closeList();
      const lvl = h[1].length;
      html += `<h${lvl}>${renderInline(h[2])}</h${lvl}>`;
      continue;
    }

    // 列表项（无序 / 有序）
    const li = line.match(/^\s*[-*]\s+(.*)$/) || line.match(/^\s*\d+\.\s+(.*)$/);
    if (li) { flushPara(); if (!listOpen) { html += "<ul>"; listOpen = true; } html += "<li>" + renderInline(li[1]) + "</li>"; continue; }

    // 空行
    if (!line.trim()) { flushPara(); closeList(); continue; }

    // 普通段落行（行内公式/代码保留在同一段落，不换行）
    closeList();
    para.push(line);
  }
  if (inCode) html += `<pre class="md-code"><code>${esc(codeBuf)}</code></pre>`;
  flushPara(); closeList();
  return html;
}

function fmtTs(ts) {
  try { return new Date(ts).toLocaleString(); } catch { return ts; }
}
function fmtTsShort(ts) {
  try {
    const d = new Date(ts);
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  } catch { return ts; }
}

// ---------- right rail (fills the wide-screen whitespace) ----------
async function renderRightRail() {
  const rm = $("#rrModel");
  if (rm) {
    rm.textContent = _modelInfo.text;
    rm.className = "rr-model " + (_modelInfo.cls || "muted");
  }
  // 功能工作区模式下不渲染右侧栏
  if (document.body.classList.contains("fw-mode")) return;
  // 最近动态（统一四模块历史）
  try {
    const r = await fetch("/api/history");
    const d = await r.json();
    window._history = d.items || [];
    const rc = parseInt(localStorage.getItem("hy3-recent-count"), 10);
    const list = window._history.slice(0, (rc > 0 ? rc : 6));
    const box = $("#rrRecent");
    if (!list.length) { box.innerHTML = `<div class="rr-empty">暂无记录</div>`; return; }
    const labelMap = { research: "深度研究", search: "检索", smart: "检索", paper: "论文", studio: "写作", advisor: "思路提炼" };
    box.innerHTML = list.map((h) => {
      return `<div class="rr-item" data-ts="${esc(h.ts)}">
        <span class="rr-dot rr-${h.kind}"></span>
        <div class="rr-txt"><div class="rr-t">${esc(trunc(h.title, 26))}</div>
        <div class="rr-s">${labelMap[h.kind] || h.kind} · ${fmtTs(h.ts)}</div></div>
      </div>`;
    }).join("");
    box.querySelectorAll(".rr-item").forEach((el) => el.addEventListener("click", () => {
      const idx = window._history.findIndex((x) => x.ts === el.dataset.ts);
      if (idx >= 0) openHistory(idx);
    }));
  } catch {}
}

// ========================================
// Feature Workspace · 独立功能工作区
// ========================================
let fwState = {
  feature: null,
  layout: "chat",
  chatHistory: [],
  papers: [],
  activePaper: null,
  cdCode: "",
  messages: [],
  standalone: false,
};

function getLayoutType(f) {
  if (f.layout_type) return f.layout_type;
  if (f.ui && f.ui.layout && typeof f.ui.layout === "string") return f.ui.layout;
  return "chat";
}

async function enterFeatureWorkspace(id) {
  let f;
  try {
    const r = await fetch("/api/features/" + id);
    const d = await r.json();
    f = d.feature;
  } catch (e) {
    toast("功能不存在", true);
    exitFeatureWorkspace();
    return;
  }
  if (!f) { toast("功能不存在", true); exitFeatureWorkspace(); return; }

  fwState.feature = f;
  fwState.layout = getLayoutType(f);
  fwState.chatHistory = [];
  fwState.papers = [];
  fwState.activePaper = null;
  fwState.messages = [];

  // 标记为功能工作区模式，隐藏侧边栏和右侧栏
  document.body.classList.add("fw-mode");

  // 隐藏所有其他view，显示view-feature
  $$(".view").forEach((v) => v.classList.add("hidden"));
  $("#view-feature").classList.remove("hidden");

  // 设置工具栏
  $("#fwEmoji").textContent = f.emoji || "🧩";
  $("#fwName").textContent = f.name || "Feature";
  $("#fwBreadcrumb").innerHTML = "AI Feature Studio · <span id=\"fwVersion\">v" + esc(f.version || "1.0.0") + "</span>";

  // 收藏状态
  const favBtn = $("#fwFavBtn");
  if (f.favorited) favBtn.classList.add("active");
  else favBtn.classList.remove("active");

  // 隐藏所有布局，显示对应布局
  $$(".fw-layout").forEach((l) => l.classList.add("hidden"));
  const targetLayout = $(".fw-layout[data-layout=\"" + fwState.layout + "\"]");
  if (targetLayout) targetLayout.classList.remove("hidden");
  else $(".fw-layout[data-layout=\"chat\"]").classList.remove("hidden");

  // 隐藏详情面板
  $("#fwInfoPanel").classList.add("hidden");

  // 初始化对应布局
  initFeatureLayout(f);

  // 使用次数+1
  try { fetch("/api/features/" + id + "/use", { method: "POST" }); } catch(e){}

  window.scrollTo(0, 0);
}

function exitFeatureWorkspace() {
  document.body.classList.remove("fw-mode");
  fwState.feature = null;
  $$(".fw-layout").forEach((l) => l.classList.add("hidden"));
  $("#view-feature").classList.add("hidden");
  $("#fwInfoPanel").classList.add("hidden");
  if (fwState.standalone) {
    fwState.standalone = false;
    location.href = "/";
    return;
  }
  if (location.hash.startsWith("#/feature/")) {
    history.replaceState(null, "", location.pathname + location.search);
  }
  switchView("forge");
}

function initFeatureLayout(f) {
  const layout = fwState.layout;

  // 通用：设置starters到chat布局
  if (f.starters && f.starters.length) {
    const sc = $("#fwChatStarters");
    if (sc) sc.innerHTML = f.starters.map((s) => `<button class="res-starter-chip" data-starter="${esc(s)}">${esc(s)}</button>`).join("");
  }
  $("#fwChatEmoji").textContent = f.emoji || "🧩";
  $("#fwChatTitle").textContent = f.name || "开始对话";
  $("#fwChatDesc").textContent = f.description || "描述你的需求，AI 将为你提供帮助";
  $("#fwChatMessages").innerHTML = "";
  $("#fwChatMessages").classList.add("hidden");
  $("#fwChatWelcome").classList.remove("hidden");

  if (layout === "research") {
    initResearchLayout(f);
  } else if (layout === "review") {
    initReviewLayout(f);
  } else if (layout === "experiment") {
    initExperimentLayout(f);
  } else if (layout === "meeting") {
    initMeetingLayout(f);
  } else if (layout === "medical") {
    initMedicalLayout(f);
  } else if (layout === "coding") {
    initCodingLayout(f);
  }

  // 清空各个输入框状态
  $("#fwChatInput").value = "";
}

// --- Research Layout ---
function initResearchLayout(f) {
  const starters = $("#resStarters");
  if (starters && f.starters) {
    starters.innerHTML = f.starters.map((s) => `<button class="res-starter-chip" data-res-starter="${esc(s)}">${esc(s)}</button>`).join("");
  }
  // 绑定tab切换
  $$(".res-tab").forEach((t) => {
    t.onclick = () => {
      $$(".res-tab").forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      const name = t.dataset.restab;
      $$(".res-tab-pane").forEach((p) => p.classList.toggle("active", p.dataset.restabpane === name));
    };
  });
  // 示例论文
  $("#resAddDemo").onclick = () => {
    fwState.papers = [
      { id: "demo1", title: "Attention Is All You Need", authors: "Vaswani et al.", year: "2017", content: "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks... We propose a new simple network architecture, the Transformer, based solely on attention mechanisms." },
      { id: "demo2", title: "BERT: Pre-training of Deep Bidirectional Transformers", authors: "Devlin et al.", year: "2019", content: "We introduce a new language representation model called BERT, which stands for Bidirectional Encoder Representations from Transformers." },
    ];
    renderResPaperList();
  };
  // starter chip点击
  $("#resStarters").onclick = (e) => {
    const chip = e.target.closest(".res-starter-chip");
    if (chip) sendResChat(chip.dataset.resStarter);
  };
  $("#resSendBtn").onclick = () => {
    const inp = $("#resChatInput");
    if (inp.value.trim()) { sendResChat(inp.value.trim()); inp.value = ""; }
  };
  $("#resChatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); $("#resSendBtn").click(); }
  });
}
function renderResPaperList() {
  const list = $("#resPaperList");
  if (!fwState.papers.length) return;
  list.innerHTML = fwState.papers.map((p) =>
    `<div class="res-paper-item ${fwState.activePaper === p.id ? "active" : ""}" data-pid="${p.id}">
      <div class="res-paper-title">${esc(p.title)}</div>
      <div class="res-paper-meta">${esc(p.authors)} · ${esc(p.year)}</div>
    </div>`
  ).join("");
  list.querySelectorAll(".res-paper-item").forEach((el) => el.onclick = () => {
    fwState.activePaper = el.dataset.pid;
    list.querySelectorAll(".res-paper-item").forEach((x) => x.classList.toggle("active", x.dataset.pid === el.dataset.pid));
    const p = fwState.papers.find((x) => x.id === el.dataset.pid);
    if (p) {
      $("#resReaderTitle").textContent = "📖 " + p.title;
      $(".res-reader-placeholder").classList.add("hidden");
      $("#resReaderContent").classList.remove("hidden");
      $("#resReaderContent").innerHTML = `<h2>${esc(p.title)}</h2><p style="color:#8b949e">${esc(p.authors)} · ${esc(p.year)}</p><hr style="border-color:#21262d;margin:16px 0"><p>${esc(p.content)}</p>`;
      $("#resOutline").innerHTML = "<p style='color:#38e1c4'>• 摘要与引言<br>• 相关工作<br>• 方法（Transformer架构）<br>• 实验<br>• 结论</p>";
    }
  });
  if (fwState.papers.length && !fwState.activePaper) {
    list.querySelector(".res-paper-item").click();
  }
}
async function sendResChat(msg) {
  if (!fwState.feature) return;
  const msgs = $("#resAiNotes");
  msgs.innerHTML = "<div style='color:#38e1c4'>🤔 思考中...</div>";
  try {
    let resp;
    if (!window._modelInfo || window._modelInfo.cls === "err") {
      msgs.innerHTML = "<p>这是科研工作区示例回复。配置API Key后可获得真实AI回答。当前文献：" + (fwState.activePaper ? fwState.papers.find(p=>p.id===fwState.activePaper)?.title : "未选择") + "</p>";
      return;
    }
    resp = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: "请基于科研工作区的上下文回答：" + msg + (fwState.activePaper ? "\n\n当前阅读：" + fwState.papers.find(p=>p.id===fwState.activePaper)?.title : ""),
        history: fwState.chatHistory, system_prompt: fwState.feature.prompt,
      }),
    });
    const d = await resp.json();
    msgs.innerHTML = "<p>" + esc(d.reply || "已处理") + "</p>";
    fwState.chatHistory.push({ role: "user", content: msg }, { role: "assistant", content: d.reply || "" });
  } catch(e) { msgs.innerHTML = "<p style='color:#ff6b6b'>请求失败，请检查API配置</p>"; }
}

// --- Review Layout ---
function initReviewLayout(f) {
  $("#revMain").classList.add("hidden");
  $("#revUploadArea").classList.remove("hidden");
  $("#revPaperText").value = "";
  // 滑动条评分
  [1,2,3,4].forEach((i) => {
    const slider = $("#revSlider" + i);
    const val = $("#revScore" + i);
    slider.oninput = () => { val.textContent = slider.value + "/10"; };
  });
  $("#revStartBtn").onclick = () => {
    if (!$("#revPaperText").value.trim()) { toast("请粘贴论文文本", true); return; }
    $("#revUploadArea").classList.add("hidden");
    $("#revMain").classList.remove("hidden");
  };
  $("#revGenBtn").onclick = generateReview;
}
async function generateReview() {
  const out = $("#revOutput");
  out.innerHTML = "<div style='text-align:center;padding:40px;color:#f78fb3'>🤖 AI 审稿中...</div>";
  await new Promise((r) => setTimeout(r, 1500));
  const s1 = +$("#revSlider1").value || 7;
  const s2 = +$("#revSlider2").value || 6;
  const s3 = +$("#revSlider3").value || 7;
  const s4 = +$("#revSlider4").value || 8;
  const avg = ((s1+s2+s3+s4)/4).toFixed(1);
  const dec = $("#revDecision").value || "borderline";
  const decMap = { accept: "✅ Accept", "weak-accept": "🟢 Weak Accept", borderline: "🟡 Borderline", "weak-reject": "🟠 Weak Reject", reject: "❌ Reject" };
  out.innerHTML = `
    <div class="rev-review-content" style="font-size:13px;line-height:1.8;color:#c9d1d9">
      <h3 style="color:#f78fb3;margin-top:0">📋 审稿意见</h3>
      <p><b>综合评分：</b>${avg}/10</p>
      <p><b>最终建议：</b>${decMap[dec]}</p>
      <h4 style="color:#f78fb3">1. 主要贡献</h4>
      <ul><li>论文提出了一个有趣的研究问题，具有一定的新颖性。</li><li>方法设计有一定创新性，实验部分覆盖了主要对比基线。</li></ul>
      <h4 style="color:#f78fb3">2. 主要弱点</h4>
      <ul><li>部分实验设置描述不够清晰，可复现性存疑。</li><li>与最新相关工作的对比不够充分。</li><li>消融实验可以进一步完善以验证各模块贡献。</li></ul>
      <h4 style="color:#f78fb3">3. 改进建议</h4>
      <ul><li>建议补充更多 ablation study。</li><li>建议增加在更大规模数据集上的实验。</li><li>建议完善错误分析，讨论方法的局限性。</li></ul>
      <p style="color:#8b949e;font-size:12px;margin-top:16px">* 以上为AI生成的示例审稿意见，仅供参考。</p>
    </div>`;
}

// --- Experiment Layout ---
function initExperimentLayout(f) {
  const starters = $("#expStarters");
  if (starters && f.starters) {
    starters.innerHTML = f.starters.map((s) => `<button class="res-starter-chip">${esc(s)}</button>`).join("");
  }
  $("#expGenWorkflow").onclick = generateExperiment;
}
async function generateExperiment() {
  const q = $("#expQuestion").value.trim();
  if (!q) { toast("请先描述研究问题", true); return; }
  $("#expSteps").innerHTML = "<div style='text-align:center;padding:40px;color:#f7c948'>🧪 生成实验流程中...</div>";
  await new Promise((r) => setTimeout(r, 1000));
  const steps = [
    { title: "实验准备", desc: "确定实验环境、工具和材料，准备被试招募或数据集。" },
    { title: "预实验 / Pilot Study", desc: "进行小样本预实验，验证实验流程可行性，调整参数。" },
    { title: "正式实验", desc: "按照设计方案执行主实验，记录自变量操纵和因变量测量。" },
    { title: "数据收集", desc: "收集实验数据，进行清洗和预处理，剔除异常值。" },
    { title: "统计分析", desc: "使用描述统计、推断统计（t检验/ANOVA/回归等）分析数据。" },
    { title: "结果解读", desc: "解读分析结果，验证/拒绝研究假设，得出结论。" },
  ];
  $("#expSteps").innerHTML = steps.map((s, i) =>
    `<div class="exp-step-card">
      <div class="exp-step-num">${i+1}</div>
      <div class="exp-step-content">
        <div class="exp-step-title">${esc(s.title)}</div>
        <div class="exp-step-desc">${esc(s.desc)}</div>
      </div>
    </div>`).join("");
  $("#expGantt").html = "";
  $("#expGantt").innerHTML = `<div>📅 <b>第1-2周</b>：准备阶段<br>📅 <b>第3周</b>：预实验<br>📅 <b>第4-6周</b>：正式实验<br>📅 <b>第7周</b>：数据分析<br>📅 <b>第8周</b>：撰写报告</div>`;
  $("#expAnalysis").innerHTML = "<div>📊 建议分析方法：<br>• 描述性统计<br>• 独立样本t检验 / 配对t检验<br>• 方差分析 (ANOVA)<br>• 效应量 (Cohen's d)<br>• 可视化：箱线图、柱状图</div>";
  $("#expConfounds").innerHTML = "<div>⚠️ 注意混淆因素：<br>• 顺序效应（建议counterbalance）<br>• 练习效应 / 疲劳效应<br>• 期望效应（双盲设计）<br>• 样本偏差</div>";
}

// --- Meeting Layout ---
function initMeetingLayout(f) {
  $("#mtAnalyzeBtn").onclick = analyzeMeeting;
}
async function analyzeMeeting() {
  const text = $("#mtTranscript").value.trim();
  if (!text) { toast("请粘贴会议文字记录", true); return; }
  const s = $("#mtSummary");
  s.innerHTML = "<div class='mt-waiting'><div class='mt-waiting-icon'>⏳</div><p>分析中...</p></div>";
  await new Promise((r) => setTimeout(r, 1200));
  s.innerHTML = `<div class="mt-summary-content" style="font-size:13px;line-height:1.8;color:#c9d1d9;padding:8px 0">
    <h4>📌 会议主题</h4><p>项目进度同步与下一阶段规划</p>
    <h4>💬 讨论要点</h4><ul><li>回顾了上一阶段的核心工作进展和里程碑完成情况</li><li>讨论了当前遇到的主要技术瓶颈和资源限制</li><li>明确了下一阶段需要优先推进的关键任务</li><li>确定了跨团队协作的沟通机制和对接人</li></ul>
    <h4>✅ 决策事项</h4><ul><li>下周三前完成核心功能的原型开发</li><li>增派一名工程师支持数据处理模块</li><li>每周五下午固定召开项目同步会</li></ul>
    <h4>📋 行动项</h4>
    <table class="mt-action-table"><tr><th>任务</th><th>负责人</th><th>截止日期</th></tr>
      <tr><td>完成API接口文档</td><td>张三</td><td>下周三</td></tr>
      <tr><td>准备用户测试方案</td><td>李四</td><td>下周五</td></tr>
      <tr><td>协调服务器资源</td><td>王五</td><td>本周内</td></tr>
    </table>
    <p style="color:#8b949e;font-size:12px;margin-top:16px">* 以上为AI生成的示例会议纪要</p>
  </div>`;
  $("#mtTranscriptView").classList.remove("hidden");
  $("#mtTranscriptView").innerHTML = text.split(/\n/).filter(l=>l.trim()).map((l,i) =>
    `<div class="mt-transcript-line"><span class="mt-time">${String(Math.floor(i/2)).padStart(2,'0')}:${String((i%2)*30).padStart(2,'0')}</span>${esc(l)}</div>`).join("");
  $("#mtUploadArea").classList.add("hidden");
}

// --- Medical Layout ---
function initMedicalLayout(f) {
  $("#mdGenBtn").onclick = generateMedicalReport;
}
async function generateMedicalReport() {
  const name = $("#mdName").value.trim() || "未填写";
  const cc = $("#mdCC").value.trim();
  if (!cc) { toast("请填写主诉", true); return; }
  const r = $("#mdReport");
  r.innerHTML = "<div class='md-waiting'><div class='md-waiting-icon'>🩺</div><p>生成病历中...</p></div>";
  await new Promise((res) => setTimeout(res, 1200));
  r.innerHTML = `<div class="md-report-content" style="font-size:13px;line-height:1.8;color:#c9d1d9">
    <div class="md-report-section"><h4>主诉 (CC)</h4><p>${esc(cc)}</p></div>
    <div class="md-report-section"><h4>现病史 (HPI)</h4><p>${esc($("#mdHPI").value || "根据患者主诉，建议进一步详细询问病史。")}</p></div>
    <div class="md-report-section"><h4>初步诊断（按可能性排序）</h4>
      <ol class="md-diagnosis-list"><li>上呼吸道感染（可能性高）</li><li>急性支气管炎（待排除）</li><li>过敏性鼻炎（鉴别诊断）</li></ol>
    </div>
    <div class="md-report-section"><h4>鉴别诊断</h4><ul><li>流行性感冒：多伴高热、全身酸痛，可做流感病毒检测鉴别</li><li>肺炎：如有持续高热、咳脓痰，建议胸片检查</li></ul></div>
    <div class="md-report-section"><h4>诊疗计划</h4><ul><li>完善血常规、CRP检查</li><li>对症治疗：退热、止咳、补液</li><li>注意休息，多饮水</li><li>如症状持续3天无缓解或加重，及时复诊</li></ul></div>
    <p style="color:#ff6b6b;font-size:11px;margin-top:20px;padding:10px;background:rgba(255,107,107,0.08);border-radius:8px">⚠️ 免责声明：本报告由AI辅助生成，仅供临床参考，不构成正式医疗诊断。请以执业医师的诊断为准。</p>
  </div>`;
}

// --- Coding Layout ---
function initCodingLayout(f) {
  const starters = $("#cdStarters");
  if (starters && f.starters) {
    starters.innerHTML = f.starters.map((s) => `<button class="res-starter-chip" data-cd-starter="${esc(s)}">${esc(s)}</button>`).join("");
  }
  // 文件树点击
  $$(".cd-tree-item.cd-file").forEach((el) => el.onclick = () => {
    $$(".cd-tree-item.cd-file").forEach((x) => x.classList.remove("active"));
    el.classList.add("active");
  });
  // 运行按钮
  $("#cdRunBtn").onclick = () => {
    const term = $("#cdTerminal");
    const line = document.createElement("div");
    line.className = "cd-term-line";
    line.innerHTML = `<span class="cd-term-prompt">$</span> <span class="cd-term-cmd">python main.py</span>`;
    term.insertBefore(line, term.lastElementChild);
    const out = document.createElement("div");
    out.className = "cd-term-output";
    out.textContent = "55";
    term.insertBefore(out, term.lastElementChild);
    term.scrollTop = term.scrollHeight;
  };
  // AI发送
  $("#cdSendBtn").onclick = () => {
    const inp = $("#cdAiInput");
    if (inp.value.trim()) { sendCodingChat(inp.value.trim()); inp.value = ""; }
  };
  $("#cdAiInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#cdSendBtn").click(); }
  });
  $("#cdStarters").onclick = (e) => {
    const chip = e.target.closest(".res-starter-chip");
    if (chip) sendCodingChat(chip.dataset.cdStarter);
  };
}
function appendCdMsg(role, text) {
  const box = $("#cdAiMessages");
  const el = document.createElement("div");
  el.className = "cd-ai-msg " + (role === "user" ? "cd-ai-user" : "cd-ai-assistant");
  el.innerHTML = `<div class="cd-ai-avatar">${role === "user" ? "👤" : "🤖"}</div><div class="cd-ai-bubble">${esc(text)}</div>`;
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
}
async function sendCodingChat(msg) {
  appendCdMsg("user", msg);
  await new Promise((r) => setTimeout(r, 800));
  appendCdMsg("assistant", "这是一个示例回复。配置API Key后我可以帮你：\n• 解释代码逻辑\n• 诊断和修复Bug\n• 重构代码\n• 生成单元测试\n\n请描述你的具体需求，我来帮你！");
}

// --- Chat Layout（通用兜底）---
function appendFwMsg(role, text) {
  $("#fwChatWelcome").classList.add("hidden");
  const box = $("#fwChatMessages");
  box.classList.remove("hidden");
  const el = document.createElement("div");
  el.className = "fw-msg fw-msg-" + role;
  el.innerHTML = `<div class="fw-msg-avatar">${role === "user" ? "👤" : (fwState.feature?.emoji || "🧩")}</div><div class="fw-msg-bubble">${esc(text)}</div>`;
  box.appendChild(el);
  box.parentElement.scrollTop = box.parentElement.scrollHeight;
}
async function sendFwChat(msg) {
  if (!fwState.feature) return;
  appendFwMsg("user", msg);
  if (!window._modelInfo || window._modelInfo.cls === "err") {
    appendFwMsg("assistant", "你好！这是「" + (fwState.feature.name) + "」功能。" + (fwState.feature.description || "") + "\n\n请先配置API Key以获得完整AI能力。");
    return;
  }
  try {
    const resp = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg, history: fwState.messages, system_prompt: fwState.feature.prompt }),
    });
    const d = await resp.json();
    appendFwMsg("assistant", d.reply || "已处理");
    fwState.messages.push({ role: "user", content: msg }, { role: "assistant", content: d.reply || "" });
  } catch(e) { appendFwMsg("assistant", "请求失败"); }
}

// --- 功能详情面板 ---
function toggleFeatureInfo() {
  const f = fwState.feature;
  if (!f) return;
  const panel = $("#fwInfoPanel");
  panel.classList.toggle("hidden");
  if (panel.classList.contains("hidden")) return;
  $("#fwInfoName").textContent = f.name;
  const catLbl = CAT_LABEL[f.category] || f.category || "其他";
  $("#fwInfoBody").innerHTML = `
    <div class="fw-info-section">
      <h4>关于此功能</h4>
      <p>${esc(f.description || "暂无描述")}</p>
    </div>
    <div class="fw-info-section">
      <h4>统计数据</h4>
      <div class="fw-info-stats">
        <div class="fw-info-stat"><div class="fw-info-stat-num">${f.use_count || 0}</div><div class="fw-info-stat-label">使用次数</div></div>
        <div class="fw-info-stat"><div class="fw-info-stat-num">${f.forks || 0}</div><div class="fw-info-stat-label">Fork</div></div>
        <div class="fw-info-stat"><div class="fw-info-stat-num">${f.rating_count ? f.rating.toFixed(1) : "--"}</div><div class="fw-info-stat-label">评分</div></div>
        <div class="fw-info-stat"><div class="fw-info-stat-num">${f.rating_count || 0}</div><div class="fw-info-stat-label">评价数</div></div>
      </div>
    </div>
    <div class="fw-info-section">
      <h4>信息</h4>
      <div class="fw-info-meta-row"><span>分类</span><span>${esc(catLbl)}</span></div>
      <div class="fw-info-meta-row"><span>版本</span><span>v${esc(f.version || "1.0.0")}</span></div>
      <div class="fw-info-meta-row"><span>作者</span><span>${f.creator === "system" ? "Hy3 官方" : esc(f.creator)}</span></div>
      <div class="fw-info-meta-row"><span>标签</span><span>${(f.tags || []).map(t => `<span class="fw-info-tag">${esc(t)}</span>`).join("")}</span></div>
    </div>
  `;
}

// --- hash路由 ---
function handleHashRoute() {
  const hash = location.hash;
  const fm = hash.match(/^#\/feature\/([^/]+)$/);
  if (fm) {
    if (fwState.feature && fwState.feature.id === fm[1]) return;
    enterFeatureWorkspace(fm[1]);
  } else if (document.body.classList.contains("fw-mode")) {
    exitFeatureWorkspace();
  }
}
window.addEventListener("hashchange", handleHashRoute);

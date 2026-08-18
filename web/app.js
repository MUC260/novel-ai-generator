(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const chaptersSelects = [$("chapters"), $("continueChapters")];
  for (let i = 1; i <= 15; i++) {
    chaptersSelects.forEach((sel) => {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = i + " 章";
      sel.appendChild(opt);
    });
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async function api(path, options) {
    const resp = await fetch(path, options);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || data.ok === false) {
      throw new Error(data.error || ("请求失败 " + resp.status));
    }
    return data;
  }

  function setHealth(text, ok) {
    const el = $("healthText");
    el.textContent = text;
    el.style.color = ok ? "var(--ok)" : "var(--danger)";
  }

  async function refreshHealth() {
    try {
      const data = await api("/api/health");
      setHealth("模型已接入：" + data.model + " · " + data.base_url, true);
    } catch (err) {
      setHealth("连接异常：" + err.message, false);
    }
  }

  async function loadProjects() {
    const data = await api("/api/projects");
    const sel = $("continueProject");
    const list = $("projectList");
    const count = $("projectCount");
    sel.innerHTML = '<option value="">请选择工程</option>';
    list.innerHTML = "";
    count.textContent = data.projects.length ? "共 " + data.projects.length + " 个" : "暂无工程";
    data.projects.forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
      const item = document.createElement("div");
      item.className = "project-item";
      item.textContent = name;
      item.addEventListener("click", () => loadProject(name));
      list.appendChild(item);
    });
  }

  async function loadProject(name) {
    const data = await api("/api/project?name=" + encodeURIComponent(name));
    const p = data.project;
    const detail = $("projectDetail");
    const world = p.world || {};
    const chars = (p.char && p.char.characters) || [];
    const plot = p.plot || {};
    detail.innerHTML = `
      <h3>${esc(name)}</h3>
      <p>路径：${esc(p.dir)}</p>
      <p>题材：${esc((world.genre || world.world_setting && world.world_setting["世界类型"]) || "未设定")} · 文风：${esc(world.style || (world.world_setting && world.world_setting["整体基调"]) || "未设定")}</p>
      <p>人物：${chars.map((c) => esc(c["姓名"])).join("、") || "无"}</p>
      <details><summary>章节列表</summary><pre>${esc((p.chapters || []).map((c) => c.file + " · " + c.chars + " 字").join("\n") || "暂无章节")}</pre></details>
      <details><summary>世界档案 world.json</summary><pre>${esc(JSON.stringify(world, null, 2))}</pre></details>
      <details><summary>人物档案 char.json</summary><pre>${esc(JSON.stringify(p.char || {}, null, 2))}</pre></details>
      <details><summary>剧情档案 plot.json</summary><pre>${esc(JSON.stringify(plot, null, 2))}</pre></details>
    `;
  }

  function showResult(data) {
    const section = $("resultSection");
    section.classList.remove("hidden");
    const results = data.results || [];
    const lowHigh = { short: "1200-2000", standard: "3000-4000", long: "9000-11000" };
    $("resultMeta").innerHTML = "工程：<strong>" + esc(data.project.name) + "</strong> · 共 " + results.length + " 章";
    $("resultChapters").innerHTML = results.map((r) => `
      <div class="chapter-card">
        <strong>第 ${r.chapter} 章</strong>
        <span class="badge ${lowHigh[r.tier] ? "ok" : ""}">${r.chars} 字</span>
        <button class="ghost viewBtn" data-project="${esc(data.project.name)}" data-chapter="${esc(r.chapter)}" type="button">查看正文</button>
        <button class="ghost copyBtn" data-text="${esc(r.text)}" type="button">复制正文</button>
      </div>
    `).join("");
    document.querySelectorAll(".viewBtn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const project = btn.getAttribute("data-project");
        const chapter = btn.getAttribute("data-chapter");
        const d = await api("/api/chapter?project=" + encodeURIComponent(project) + "&chapter=" + encodeURIComponent("chapter_" + String(chapter).padStart(3, "0") + ".txt"));
        openModal("第 " + chapter + " 章", d.chapter);
      });
    });
    document.querySelectorAll(".copyBtn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const text = btn.getAttribute("data-text") || "";
        await navigator.clipboard.writeText(text);
        btn.textContent = "已复制";
      });
    });
    section.scrollIntoView({ behavior: "smooth" });
  }

  function openModal(title, body) {
    $("modalTitle").textContent = title;
    $("modalBody").textContent = body || "";
    $("chapterModal").classList.remove("hidden");
  }

  function closeModal() {
    $("chapterModal").classList.add("hidden");
  }

  function collectCreate() {
    return {
      title: $("title").value.trim(),
      mode: $("mode").value,
      chapters: Number($("chapters").value),
      tier: $("tier").value,
      genre: $("genre").value.trim(),
      style: $("style").value.trim(),
      world: $("world").value.trim(),
      rules: $("rules").value.trim(),
      power: $("power").value.trim(),
      forces: $("forces").value.trim(),
      protagonist: $("protagonist").value.trim(),
      side_characters: $("side_characters").value.trim(),
      antagonist: $("antagonist").value.trim(),
      opening: $("opening").value.trim(),
      conflict: $("conflict").value.trim(),
      relations: $("relations").value.trim(),
      direction: $("direction").value.trim(),
      taboos: $("taboos").value.trim(),
      preferences: $("preferences").value.trim(),
      anti_ending: $("anti_ending").checked,
      memory_inherit: $("memory_inherit").checked,
      progression: $("progression").checked,
      de_ai: $("de_ai").checked,
      autosave: $("autosave").checked,
    };
  }

  function collectContinue() {
    return {
      project: $("continueProject").value,
      chapters: Number($("continueChapters").value),
      tier: $("continueTier").value,
      anti_ending: $("cont_anti_ending").checked,
      memory_inherit: $("cont_memory_inherit").checked,
      progression: $("cont_progression").checked,
      de_ai: $("cont_de_ai").checked,
      autosave: $("cont_autosave").checked,
    };
  }

  async function createProject() {
    const body = collectCreate();
    if (!body.title) { alert("请先填写小说名称"); return; }
    $("createBtn").disabled = true;
    $("createBtn").textContent = "生成中，请勿关闭页面...";
    try {
      const data = await api("/api/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      showResult(data);
      await loadProjects();
    } catch (err) {
      alert("生成失败：" + err.message);
    } finally {
      $("createBtn").disabled = false;
      $("createBtn").textContent = "开始生成";
    }
  }

  async function continueProject() {
    const body = collectContinue();
    if (!body.project) { alert("请先选择工程"); return; }
    $("continueBtn").disabled = true;
    $("continueBtn").textContent = "续写中，请勿关闭页面...";
    try {
      const data = await api("/api/continue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      showResult(data);
      await loadProjects();
    } catch (err) {
      alert("续写失败：" + err.message);
    } finally {
      $("continueBtn").disabled = false;
      $("continueBtn").textContent = "开始续写";
    }
  }

  async function testModel() {
    $("testBtn").disabled = true;
    $("testBtn").textContent = "检测中...";
    try {
      const data = await api("/api/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      setHealth("模型测试成功：" + (data.reply || "已连接"), true);
    } catch (err) {
      setHealth("模型测试失败：" + err.message, false);
    } finally {
      $("testBtn").disabled = false;
      $("testBtn").textContent = "测试模型";
    }
  }

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $("tab-" + btn.getAttribute("data-tab")).classList.add("active");
      if (btn.getAttribute("data-tab") === "projects") loadProjects();
    });
  });

  $("mode").addEventListener("change", () => {
    $("customBox").open = $("mode").value === "custom";
  });

  $("testBtn").addEventListener("click", testModel);
  $("refreshBtn").addEventListener("click", () => { refreshHealth(); loadProjects(); });
  $("createBtn").addEventListener("click", createProject);
  $("continueBtn").addEventListener("click", continueProject);
  $("closeResult").addEventListener("click", () => $("resultSection").classList.add("hidden"));
  $("closeModal").addEventListener("click", closeModal);
  $("chapterModal").addEventListener("click", (e) => { if (e.target === $("chapterModal")) closeModal(); });

  refreshHealth();
  loadProjects();
})();

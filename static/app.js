document.addEventListener("DOMContentLoaded", () => {
  const LOCK_TIMEOUT_MS = 30000;
  const formLocks = new WeakMap();

  const heroStatus = document.querySelector("#hero-status");
  const heroTitle = document.querySelector("#hero-title");
  const heroDetail = document.querySelector("#hero-detail");
  const heroMeta = document.querySelector("#hero-meta");

  const runtimePendingBanner = document.querySelector("#runtime-pending-banner");
  const summaryGrid = document.querySelector("#summary-grid");
  const workspace = document.querySelector("#workspace");
  const pendingWorkspace = document.querySelector("#pending-workspace");

  function snapshotSections() {
    return {
      summaryHidden: summaryGrid ? summaryGrid.hidden : false,
      summaryHtml: summaryGrid ? summaryGrid.innerHTML : "",
      workspaceHidden: workspace ? workspace.hidden : false,
      workspaceHtml: workspace ? workspace.innerHTML : "",
    };
  }

  function restoreSections(snapshot) {
    if (!snapshot) return;
    if (summaryGrid) {
      summaryGrid.hidden = Boolean(snapshot.summaryHidden);
      summaryGrid.innerHTML = snapshot.summaryHtml || "";
    }
    if (workspace) {
      workspace.hidden = Boolean(snapshot.workspaceHidden);
      workspace.innerHTML = snapshot.workspaceHtml || "";
    }
  }

  function clearStaleSections() {
    if (summaryGrid) {
      summaryGrid.innerHTML = "";
      summaryGrid.hidden = true;
    }
    if (workspace) {
      workspace.innerHTML = "";
      workspace.hidden = true;
    }
  }

  function setRuntimePendingMode(active) {
    const pending = Boolean(active);
    document.body.classList.toggle("runtime-pending", pending);
    if (runtimePendingBanner) runtimePendingBanner.hidden = !pending;
    if (pendingWorkspace) pendingWorkspace.hidden = !pending;
    if (!pending) {
      if (summaryGrid) summaryGrid.hidden = false;
      if (workspace) workspace.hidden = false;
    }
  }

  function restoreAutoLockedControls(root) {
    root
      .querySelectorAll("button[data-auto-locked='true'], input[type='submit'][data-auto-locked='true']")
      .forEach((control) => {
        control.disabled = false;
        control.removeAttribute("data-auto-locked");
        control.classList.remove("is-submitting");
        const originalLabel = control.getAttribute("data-original-label");
        if (!originalLabel) return;
        if (control.tagName === "BUTTON") {
          control.textContent = originalLabel;
        } else {
          control.value = originalLabel;
        }
        control.removeAttribute("data-original-label");
      });

    root.querySelectorAll("form[data-form-submitting='true']").forEach((form) => {
      form.removeAttribute("data-form-submitting");
    });
  }

  function unlockForm(form) {
    const lock = formLocks.get(form);
    if (lock && typeof lock.timerId === "number") {
      window.clearTimeout(lock.timerId);
    }
    if (lock && lock.snapshot) {
      restoreSections(lock.snapshot);
    }
    restoreAutoLockedControls(form);
    formLocks.delete(form);
    setRuntimePendingMode(false);
  }

  function lockFormSubmitter(form, submitter) {
    if (!submitter) return true;
    const existing = formLocks.get(form);
    if (existing && existing.locked) return false;

    const snapshot = snapshotSections();

    form.setAttribute("data-form-submitting", "true");
    submitter.disabled = true;
    submitter.setAttribute("data-auto-locked", "true");
    submitter.classList.add("is-submitting");

    const runningLabel = submitter.getAttribute("data-running-label") || "运行中...";
    if (submitter.tagName === "BUTTON") {
      const origin = submitter.textContent || "";
      submitter.setAttribute("data-original-label", origin);
      submitter.textContent = runningLabel;
    } else {
      const origin = submitter.value || "";
      submitter.setAttribute("data-original-label", origin);
      submitter.value = runningLabel;
    }

    clearStaleSections();
    setRuntimePendingMode(true);

    const timerId = window.setTimeout(() => {
      unlockForm(form);
    }, LOCK_TIMEOUT_MS);

    formLocks.set(form, { locked: true, timerId, snapshot });
    return true;
  }

  function setHeroPendingState(form) {
    if (!heroStatus || !heroTitle || !heroDetail || !heroMeta) return;
    const pendingTitle = form.getAttribute("data-pending-title");
    const pendingDetail = form.getAttribute("data-pending-detail");
    if (!pendingTitle || !pendingDetail) return;

    heroStatus.className = "status status-pending";
    heroStatus.textContent = "运行中";
    heroTitle.textContent = pendingTitle;
    heroDetail.textContent = pendingDetail;
    heroMeta.textContent = "上一轮结果已清空，等待本轮返回。";
  }

  restoreAutoLockedControls(document);
  setRuntimePendingMode(false);

  window.addEventListener("pageshow", () => {
    restoreAutoLockedControls(document);
    setRuntimePendingMode(false);
  });

  window.addEventListener("pagehide", () => {
    setRuntimePendingMode(false);
  });

  document.querySelectorAll("form[method='post']").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const message = form.getAttribute("data-confirm");
      if (message && !window.confirm(message)) {
        event.preventDefault();
        return;
      }

      const submitter = event.submitter || form.querySelector("button[type='submit'], input[type='submit']");
      if (!lockFormSubmitter(form, submitter)) {
        event.preventDefault();
        return;
      }
      setHeroPendingState(form);
    });
  });

  window.addEventListener("beforeunload", () => {
    document.querySelectorAll("form[method='post']").forEach((form) => {
      const lock = formLocks.get(form);
      if (lock && lock.snapshot) {
        restoreSections(lock.snapshot);
      }
      restoreAutoLockedControls(form);
    });
  });
});

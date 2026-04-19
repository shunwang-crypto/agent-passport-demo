document.addEventListener("DOMContentLoaded", () => {
  function setSubmittingState(form, submitter) {
    if (!submitter) return;
    if (form.dataset.formSubmitting === "true") return;

    form.dataset.formSubmitting = "true";
    submitter.disabled = true;
    submitter.classList.add("is-submitting");

    const runningLabel = submitter.getAttribute("data-running-label");
    if (!runningLabel) return;

    if (submitter.tagName === "BUTTON") {
      submitter.dataset.originalLabel = submitter.textContent || "";
      submitter.textContent = runningLabel;
      return;
    }

    submitter.dataset.originalLabel = submitter.value || "";
    submitter.value = runningLabel;
  }

  function restoreSubmittingState(root) {
    root
      .querySelectorAll("button.is-submitting, input[type='submit'].is-submitting")
      .forEach((control) => {
        control.disabled = false;
        control.classList.remove("is-submitting");
        const originalLabel = control.dataset.originalLabel || "";
        if (!originalLabel) return;
        if (control.tagName === "BUTTON") {
          control.textContent = originalLabel;
        } else {
          control.value = originalLabel;
        }
        delete control.dataset.originalLabel;
      });

    root.querySelectorAll("form[data-form-submitting='true']").forEach((form) => {
      delete form.dataset.formSubmitting;
    });
  }

  restoreSubmittingState(document);

  window.addEventListener("pageshow", () => {
    restoreSubmittingState(document);
  });

  document.querySelectorAll("form[method='post']").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const confirmText = form.getAttribute("data-confirm");
      if (confirmText && !window.confirm(confirmText)) {
        event.preventDefault();
        return;
      }

      const submitter =
        event.submitter || form.querySelector("button[type='submit'], input[type='submit']");
      setSubmittingState(form, submitter);
    });
  });
});

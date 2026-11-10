/**
 * Participants : affiche les critères selon la note (liste déroulante).
 * Séance : libellé dynamique sous les boutons radio de satisfaction.
 */
(() => {
  function readNoteLabels() {
    const el = document.getElementById("eval-note-labels-json");
    if (!el) return {};
    try {
      return JSON.parse(el.textContent || "{}");
    } catch {
      return {};
    }
  }

  function bindSessionSatisfaction(form) {
    const radios = form.querySelectorAll('input[name="note_seance"][type="radio"]');
    if (!radios.length) return;

    const caption = form.querySelector(".eval-satisfaction-live");
    const labels = readNoteLabels();
    const placeholder =
      (caption && caption.getAttribute("data-placeholder")) || "Choisis une note ci-dessus.";

    function sync() {
      if (!caption) return;
      const c = form.querySelector('input[name="note_seance"]:checked');
      if (c) {
        const k = String(c.value);
        caption.textContent = labels[k] ?? labels[parseInt(k, 10)] ?? "";
      } else {
        caption.textContent = placeholder;
      }
    }

    radios.forEach((r) => r.addEventListener("change", sync));
    sync();
  }

  function syncTagPanels(form) {
    const sel = form.querySelector(".eval-note-select");
    if (!sel) return;

    const raw = sel.value;
    const n = raw === "" ? NaN : parseInt(raw, 10);
    const ok = Number.isFinite(n) && n >= 1 && n <= 5;

    form.querySelectorAll(".eval-tags-panel").forEach((panel) => {
      const pn = parseInt(panel.getAttribute("data-for-note"), 10);
      const active = ok && pn === n;
      panel.hidden = !active;
      panel.querySelectorAll("input[type='checkbox']").forEach((cb) => {
        cb.disabled = !active;
      });
    });

    form.querySelectorAll(".eval-tag").forEach((lab) => {
      const cb = lab.querySelector("input[type='checkbox']");
      if (!cb) return;
      lab.classList.toggle("is-on", cb.checked && !cb.disabled);
    });
  }

  function bindParticipantForm(form) {
    const sel = form.querySelector(".eval-note-select");
    if (!sel) return;

    sel.addEventListener("change", () => syncTagPanels(form));
    form.addEventListener("change", (e) => {
      if (e.target && e.target.matches(".eval-tag input[type='checkbox']")) {
        syncTagPanels(form);
      }
    });
    syncTagPanels(form);
  }

  document.querySelectorAll(".eval-session-form").forEach(bindSessionSatisfaction);
  document.querySelectorAll(".eval-card-form").forEach(bindParticipantForm);
})();

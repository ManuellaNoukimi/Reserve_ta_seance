(() => {
  const dialog = document.getElementById("createDialog");
  const openBtn = document.getElementById("openCreateBtn");
  const closeTopBtn = document.getElementById("closeCreateTopBtn");
  const closeBottomBtn = document.getElementById("closeCreateBottomBtn");
  const form = document.getElementById("createSessionForm");
  const formError = document.getElementById("formError");
  const csigleInput = document.getElementById("csigle");
  const debutDateTimeInput = document.getElementById("debut_datetime");
  const maxParticipantsInput = document.getElementById("max_participants");

  if (
    !dialog ||
    !openBtn ||
    !closeTopBtn ||
    !closeBottomBtn ||
    !form ||
    !formError ||
    !csigleInput ||
    !debutDateTimeInput
  ) {
    return;
  }

  const showError = (message) => {
    formError.textContent = message;
    formError.classList.add("visible");
  };

  const clearError = () => {
    formError.textContent = "";
    formError.classList.remove("visible");
  };

  const openModal = () => {
    clearError();
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    }
  };

  const closeModal = () => {
    clearError();
    dialog.close();
  };

  openBtn.addEventListener("click", openModal);
  closeTopBtn.addEventListener("click", closeModal);
  closeBottomBtn.addEventListener("click", closeModal);

  if (window.location.hash === "#creer") {
    openModal();
    try {
      history.replaceState(null, "", window.location.pathname + window.location.search);
    } catch (e) {
      /* ignore */
    }
  }

  dialog.addEventListener("click", (event) => {
    const rect = dialog.getBoundingClientRect();
    const clickedInDialog =
      rect.top <= event.clientY &&
      event.clientY <= rect.top + rect.height &&
      rect.left <= event.clientX &&
      event.clientX <= rect.left + rect.width;

    if (!clickedInDialog) {
      closeModal();
    }
  });

  [csigleInput, debutDateTimeInput, maxParticipantsInput]
    .filter(Boolean)
    .forEach((input) => {
      input.addEventListener("input", clearError);
      input.addEventListener("change", clearError);
    });

  form.addEventListener("submit", (event) => {
    const csigle = csigleInput.value.trim();
    const debutDateTime = debutDateTimeInput.value.trim();
    const maxParticipantsRaw = maxParticipantsInput
      ? maxParticipantsInput.value.trim()
      : "";

    if (!csigle || !debutDateTime) {
      event.preventDefault();
      showError("Champs requis: csigle, date/heure de début.");
      return;
    }

    if (maxParticipantsRaw) {
      const value = Number(maxParticipantsRaw);
      if (!Number.isInteger(value) || value < 1 || value > 255) {
        event.preventDefault();
        showError("Le champ 'Max participants' doit être un entier entre 1 et 255.");
        return;
      }
    }

    clearError();
  });

  const helpPopover = document.getElementById("helpLangPopover");
  const helpClose = document.getElementById("helpLangClose");
  const helpToggle = document.getElementById("helpLangToggle");

  if (helpPopover && helpClose && helpToggle) {
    helpClose.addEventListener("click", () => {
      helpPopover.classList.add("is-hidden");
    });
    helpToggle.addEventListener("click", () => {
      helpPopover.classList.toggle("is-hidden");
    });
  }
})();

const state = {
  results: [],
  seed: null,
  tracks: [],
  engine: null,
  mode: "hybrid",
  loadingTimers: [],
};

const $ = (query) => document.querySelector(query);
const $$ = (query) => [...document.querySelectorAll(query)];

const elements = {
  form: $("#searchForm"),
  query: $("#query"),
  message: $("#message"),

  results: $("#results"),
  cards: $("#cards"),

  playlist: $("#playlist"),
  title: $("#playlistTitle"),
  why: $("#why"),
  seed: $("#seed"),
  songs: $("#songs"),

  playerPanel: $("#playerPanel"),
  spotifyPlayer: $("#spotifyPlayer"),
  playerTrackTitle: $("#playerTrackTitle"),
  playerTrackArtist: $("#playerTrackArtist"),
  closePlayer: $("#closePlayer"),

  loading: $("#loading"),
  loadingTitle: $("#loadingTitle"),

  again: $("#again"),
  save: $("#save"),

  modal: $("#modal"),
  close: $("#close"),
  cancel: $("#cancel"),
  saveForm: $("#saveForm"),
  playlistName: $("#name"),
  public: $("#public"),
  saveMessage: $("#saveMsg"),

  logout: $("#logout"),

  diversity: $("#diversity"),
  diversityValue: $("#diversityValue"),

  matchingPanel: $("#matchingPanel"),

  hybridControls: $("#hybridControls"),
  hybridBalance: $("#hybridBalance"),
  hybridBalanceValue: $("#hybridBalanceValue"),

  soundControls: $("#soundControls"),
  resetSoundWeights: $("#resetSoundWeights"),

  engineName: $("#engineName"),
  engineDescription: $("#engineDescription"),
  engineMeta: $("#engineMeta"),
};

const DEFAULT_SOUND_WEIGHTS = {
  tempo: 65,
  energy: 100,
  valence: 85,
  danceability: 75,
  acousticness: 55,
  instrumentalness: 45,
};


function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}


async function api(url, options = {}) {
  const response = await fetch(url, options);

  const payload = await response
    .json()
    .catch(() => ({}));

  if (!response.ok) {
    const error = new Error(
      payload.error || "Erro inesperado.",
    );

    error.payload = payload;

    throw error;
  }

  return payload;
}


function showMessage(text, success = false) {
  elements.message.textContent = text;

  elements.message.style.color = success
    ? "#1ed760"
    : "#ff8194";

  elements.message.hidden = false;
}


function clearMessage() {
  elements.message.hidden = true;
}


function clearPlaylist() {
  state.seed = null;
  state.tracks = [];
  state.engine = null;

  closePlayer();

  elements.playlist.hidden = true;

  elements.seed.innerHTML = "";
  elements.songs.innerHTML = "";
  elements.engineMeta.innerHTML = "";
  elements.engineDescription.textContent = "";
}


function setMode(mode) {
  state.mode = mode;

  $$(".mode-button").forEach((button) => {
    button.classList.toggle(
      "active",
      button.dataset.mode === mode,
    );
  });

  elements.hybridControls.hidden = mode !== "hybrid";
  elements.soundControls.hidden = mode === "listening";
}


function diversityValue() {
  return Number(elements.diversity.value || 75) / 100;
}


function listeningWeight() {
  if (state.mode === "listening") {
    return 1;
  }

  if (state.mode === "sound") {
    return 0;
  }

  // Slider is displayed as listening on the left and sound on the right.
  return 1 - (
    Number(elements.hybridBalance.value || 50) / 100
  );
}


function soundWeights() {
  const output = {};

  $$("[data-feature]").forEach((input) => {
    output[input.dataset.feature] =
      Number(input.value || 0) / 100;
  });

  return output;
}


function generationPayload() {
  return {
    seed_track_id: state.pendingSeed?.id,
    mode: state.mode,
    diversity: diversityValue(),
    listening_weight: listeningWeight(),
    sound_weights: soundWeights(),
  };
}


function resetLoadingSteps() {
  state.loadingTimers.forEach(clearTimeout);
  state.loadingTimers = [];

  $$(".loading-steps span").forEach((item) => {
    item.classList.remove(
      "active",
      "done",
    );
  });
}


function startLoading() {
  clearPlaylist();
  clearMessage();

  resetLoadingSteps();

  elements.results.hidden = true;
  elements.matchingPanel.hidden = true;
  elements.loading.hidden = false;

  const stepNames =
    state.mode === "listening"
      ? ["listening", "ranking", "playlist"]
      : state.mode === "sound"
        ? ["sound", "ranking", "playlist"]
        : ["listening", "sound", "ranking", "playlist"];

  $$(".loading-steps span").forEach((item) => {
    item.hidden = !stepNames.includes(item.dataset.step);
  });

  const stepElements = stepNames.map(
    (name) => $(`[data-step="${name}"]`),
  );

  if (stepElements[0]) {
    stepElements[0].classList.add("active");
  }

  stepElements.slice(1).forEach((item, index) => {
    const timer = setTimeout(() => {
      stepElements.forEach((element) => {
        if (element === item) {
          element.classList.add("active");
          element.classList.remove("done");
        } else if (
          stepElements.indexOf(element) <
          stepElements.indexOf(item)
        ) {
          element.classList.remove("active");
          element.classList.add("done");
        }
      });
    }, 1200 + index * 1400);

    state.loadingTimers.push(timer);
  });

  elements.loading.scrollIntoView({
    behavior: "smooth",
    block: "center",
  });
}


function stopLoading() {
  resetLoadingSteps();
  elements.loading.hidden = true;
}


function renderResults() {
  elements.cards.innerHTML = state.results
    .map((track, index) => `
      <button
        class="track"
        data-index="${index}"
        type="button"
      >

        <img
          src="${escapeHtml(track.image)}"
          alt="Capa de ${escapeHtml(track.name)}"
        >

        <div>

          <strong>
            ${escapeHtml(track.name)}
          </strong>

          <span>
            ${escapeHtml(track.artists)}
          </span>

        </div>

      </button>
    `)
    .join("");

  elements.results.hidden =
    state.results.length === 0;

  /* Hide the comparison menu as soon as search results appear.
     It comes back only when "gerar novamente" is clicked. */
  if (state.results.length > 0) {
    elements.matchingPanel.hidden = true;
  }
}


function scoreRow(track) {
  const listening =
    typeof track.listening_match === "number"
      ? Math.round(track.listening_match * 100)
      : null;

  const sound =
    typeof track.sound_match === "number"
      ? Math.round(track.sound_match * 100)
      : null;

  const overall =
    typeof track.match === "number"
      ? Math.round(track.match * 100)
      : null;

  const parts = [];

  if (listening !== null) {
    parts.push(`
      <span title="Listening similarity">
        ears ${listening}%
      </span>
    `);
  }

  if (sound !== null) {
    parts.push(`
      <span title="Sound similarity">
        wave ${sound}%
      </span>
    `);
  }

  if (overall !== null) {
    parts.push(`
      <strong title="Final ranking score">
        match ${overall}%
      </strong>
    `);
  }

  return parts.join("");
}


function renderEngineMeta() {
  if (!state.engine) {
    elements.engineMeta.innerHTML = "";
    return;
  }

  const requested = state.engine.requested_mode || "hybrid";

  const labels = {
    listening: "Listening",
    sound: "Sound",
    hybrid: "Hybrid",
  };

  const items = [
    `<span>${labels[requested] || requested}</span>`,
    `<span>${Math.round(
      (state.engine.diversity ?? diversityValue()) * 100,
    )}% diversity</span>`,
  ];

  if (requested === "hybrid") {
    items.push(
      `<span>${Math.round(
        (state.engine.listening_weight ?? 0.5) * 100,
      )}% listening</span>`,
    );

    items.push(
      `<span>${Math.round(
        (state.engine.sound_weight ?? 0.5) * 100,
      )}% sound</span>`,
    );
  }

  if (
    requested !== "listening" &&
    !state.engine.sound_available
  ) {
    items.push(
      `<span class="warning">sound fallback</span>`,
    );
  }

  elements.engineMeta.innerHTML = items.join("");
}



function spotifyEmbedUrl(track) {
  if (!track?.id) {
    return "";
  }

  return `https://open.spotify.com/embed/track/${encodeURIComponent(
    track.id,
  )}?utm_source=generator`;
}


function openPlayer(track) {
  if (!track?.id) {
    return;
  }

  elements.playerTrackTitle.textContent =
    track.name || "Track";

  elements.playerTrackArtist.textContent =
    track.artists || "";

  elements.spotifyPlayer.src =
    spotifyEmbedUrl(track);

  elements.playerPanel.hidden = false;

  elements.playerPanel.scrollIntoView({
    behavior: "smooth",
    block: "center",
  });
}


function closePlayer() {
  elements.spotifyPlayer.src = "";
  elements.playerPanel.hidden = true;
}


function renderPlaylist() {
  if (!state.seed) {
    return;
  }

  elements.title.textContent =
    `Inspirada em ${state.seed.name}`;

  elements.why.textContent =
    state.engine?.source || "Vibe Engine";

  elements.engineName.textContent =
    state.engine?.name || "Vibe Engine";

  elements.engineDescription.textContent =
    state.engine?.description || "";

  renderEngineMeta();

  elements.seed.innerHTML = `
    <img
      src="${escapeHtml(state.seed.image)}"
      alt="Capa de ${escapeHtml(state.seed.name)}"
    >

    <div>
      <small>
        música de referência
      </small>

      <h3>
        ${escapeHtml(state.seed.name)}
      </h3>

      <p>
        ${escapeHtml(state.seed.artists)}
      </p>
    </div>
  `;

  elements.songs.innerHTML = state.tracks
    .map((track, index) => {
      const position = String(index + 1)
        .padStart(2, "0");

      return `
        <article class="song">

          <span class="position">
            ${position}
          </span>

          <img
            src="${escapeHtml(track.image)}"
            alt="Capa de ${escapeHtml(track.name)}"
          >

          <div class="song-main">

            <strong>
              ${escapeHtml(track.name)}
            </strong>

            <span>
              ${escapeHtml(track.artists)}
            </span>

            ${
              track.reason
                ? `
                  <small class="reason">
                    ${escapeHtml(track.reason)}
                  </small>
                `
                : ""
            }

            <div class="score-row">
              ${scoreRow(track)}
            </div>

          </div>

          <div class="song-actions">
            <button
              class="listen"
              data-index="${index}"
              type="button"
              aria-label="Ouvir ${escapeHtml(track.name)}"
            >
              ▶ listen
            </button>

            <a
              href="${escapeHtml(track.url)}"
              target="_blank"
              rel="noopener noreferrer"
            >
              Spotify ↗
            </a>

            <button
              class="remove"
              data-index="${index}"
              type="button"
              aria-label="Remover ${escapeHtml(track.name)}"
            >
              ×
            </button>
          </div>

        </article>
      `;
    })
    .join("");

  elements.playlist.hidden = false;

  elements.playlist.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}


async function generatePlaylist(track) {
  state.pendingSeed = track;

  startLoading();

  try {
    const payload = await api(
      "/api/generate",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(
          generationPayload(),
        ),
      },
    );

    stopLoading();

    state.seed = payload.seed;
    state.tracks = payload.tracks || [];
    state.engine = payload.engine || null;

    renderPlaylist();

  } catch (error) {
    stopLoading();

    showMessage(error.message);

    elements.matchingPanel.hidden = false;
    elements.results.hidden = false;
  }
}


elements.form.addEventListener(
  "submit",
  async (event) => {
    event.preventDefault();

    clearMessage();
    clearPlaylist();

    elements.matchingPanel.hidden = false;

    const query = elements.query.value.trim();

    if (!query) {
      showMessage(
        "Digite o nome de uma música ou artista.",
      );
      return;
    }

    try {
      const payload = await api(
        `/api/search?q=${encodeURIComponent(query)}`,
      );

      state.results = payload.tracks || [];

      renderResults();

      if (state.results.length === 0) {
        showMessage(
          "Nenhuma música encontrada.",
        );
      }

    } catch (error) {
      showMessage(error.message);
    }
  },
);


elements.cards.addEventListener(
  "click",
  (event) => {
    const button = event.target.closest(".track");

    if (!button) {
      return;
    }

    const index = Number(button.dataset.index);
    const track = state.results[index];

    if (track) {
      generatePlaylist(track);
    }
  },
);


elements.songs.addEventListener(
  "click",
  (event) => {
    const listenButton = event.target.closest(".listen");

    if (listenButton) {
      const track = state.tracks[
        Number(listenButton.dataset.index)
      ];

      if (track) {
        openPlayer(track);
      }

      return;
    }

    const removeButton = event.target.closest(".remove");

    if (!removeButton) {
      return;
    }

    const removeIndex = Number(
      removeButton.dataset.index,
    );

    const removedTrack = state.tracks[removeIndex];

    state.tracks.splice(
      removeIndex,
      1,
    );

    if (
      removedTrack?.id &&
      elements.spotifyPlayer.src.includes(
        `/track/${removedTrack.id}`,
      )
    ) {
      closePlayer();
    }

    renderPlaylist();
  },
);


elements.again.addEventListener(
  "click",
  () => {
    if (!state.seed) {
      return;
    }

    state.pendingSeed = state.seed;

    elements.playlist.hidden = true;
    elements.matchingPanel.hidden = false;

    elements.matchingPanel.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  },
);


$$(".mode-button").forEach((button) => {
  button.addEventListener("click", () => {
    setMode(button.dataset.mode);
  });
});


elements.diversity.addEventListener(
  "input",
  () => {
    elements.diversityValue.textContent =
      `${elements.diversity.value}%`;
  },
);


elements.hybridBalance.addEventListener(
  "input",
  () => {
    const sound = Number(
      elements.hybridBalance.value,
    );

    const listening = 100 - sound;

    elements.hybridBalanceValue.textContent =
      `${listening}% listening / ${sound}% sound`;
  },
);


elements.resetSoundWeights.addEventListener(
  "click",
  () => {
    $$("[data-feature]").forEach((input) => {
      input.value =
        DEFAULT_SOUND_WEIGHTS[input.dataset.feature];
    });
  },
);



elements.closePlayer.addEventListener(
  "click",
  closePlayer,
);


function openModal() {
  elements.playlistName.value = state.seed
    ? `Playlist Engine — ${state.seed.name}`
    : "Playlist Engine";

  elements.saveMessage.hidden = true;
  elements.modal.classList.add("open");
}


function closeModal() {
  elements.modal.classList.remove("open");
}


elements.save.addEventListener(
  "click",
  openModal,
);

elements.close.addEventListener(
  "click",
  closeModal,
);

elements.cancel.addEventListener(
  "click",
  closeModal,
);


elements.modal.addEventListener(
  "click",
  (event) => {
    if (event.target === elements.modal) {
      closeModal();
    }
  },
);


elements.saveForm.addEventListener(
  "submit",
  async (event) => {
    event.preventDefault();

    try {
      const payload = await api(
        "/api/save",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            name: elements.playlistName.value.trim(),
            public: elements.public.checked,
            tracks: state.tracks,
          }),
        },
      );

      if (!payload.verified) {
        throw new Error(
          "Spotify did not confirm that the playlist was saved."
        );
      }

      const countText =
        typeof payload.item_count === "number"
          ? ` (${payload.item_count} tracks)`
          : "";

      if (payload.url) {
        elements.saveMessage.innerHTML = `
          Playlist saved successfully${countText}.
          <a
            href="${escapeHtml(payload.url)}"
            target="_blank"
            rel="noopener noreferrer"
          >
            Open on Spotify ↗
          </a>
        `;
      } else {
        elements.saveMessage.textContent =
          `Playlist saved successfully${countText}.`;
      }

      elements.saveMessage.style.color =
        "#1ed760";

      elements.saveMessage.hidden = false;

    } catch (error) {
      if (error.payload?.login_required) {
        window.location.href = "/login";
        return;
      }

      elements.saveMessage.textContent =
        error.message;

      elements.saveMessage.style.color =
        "#ff8194";

      elements.saveMessage.hidden = false;
    }
  },
);


if (elements.logout) {
  elements.logout.addEventListener(
    "click",
    async () => {
      try {
        await api(
          "/logout",
          {
            method: "POST",
          },
        );

        window.location.reload();

      } catch (error) {
        showMessage(error.message);
      }
    },
  );
}


const parameters = new URLSearchParams(
  window.location.search,
);


if (parameters.get("connected")) {
  showMessage(
    "Spotify conectado. Agora você pode salvar playlists.",
    true,
  );

  window.history.replaceState(
    {},
    "",
    window.location.pathname,
  );
}


if (parameters.get("error")) {
  showMessage(
    "Não foi possível conectar ao Spotify.",
  );

  window.history.replaceState(
    {},
    "",
    window.location.pathname,
  );
}


setMode("hybrid");
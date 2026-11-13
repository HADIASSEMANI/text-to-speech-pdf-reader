(() => {
  'use strict';
  document.documentElement.classList.add('js');

  const override = new URLSearchParams(location.search).get('os');
  const detectOS = () => {
    if (['windows', 'macos', 'linux', 'mobile'].includes(override)) return override;
    const platform = navigator.userAgentData?.platform || navigator.platform || navigator.userAgent;
    if (/Android|iPhone|iPad|iPod/i.test(`${platform} ${navigator.userAgent}`)
      || (/Mac/i.test(platform) && navigator.maxTouchPoints > 1)) return 'mobile';
    if (/Win/i.test(platform)) return 'windows';
    if (/Mac/i.test(platform)) return 'macos';
    if (/Linux/i.test(platform)) return 'linux';
    return 'unknown';
  };

  const os = detectOS();
  document.documentElement.dataset.os = os;
  const components = [...document.querySelectorAll('[data-smart-download]')];
  let selected = os;
  let intelMac = false;

  const renderDownloads = () => components.forEach((component) => {
    const compact = component.classList.contains('smart-compact');
    const choice = compact ? os : selected;
    const installer = ['windows', 'macos'].includes(choice);
    const message = component.querySelector('.download-message');
    message.textContent = os === 'linux' ? 'Book TTS Reader has installers for Windows and macOS'
      : os === 'mobile' ? 'Book TTS Reader is a desktop app. Send yourself the link, or pick an installer:' : '';
    message.hidden = !message.textContent;

    component.querySelectorAll('[data-platform]').forEach((link) => {
      const platform = link.dataset.platform;
      const fallback = compact && !installer;
      link.hidden = fallback ? platform !== 'windows' : installer && platform !== choice;
      const primary = installer ? platform === choice : fallback && platform === 'windows';
      link.classList.toggle('primary', primary && !link.classList.contains('pill-cta'));
      link.classList.toggle('secondary', !primary && !link.classList.contains('pill-cta'));
      link.href = fallback ? '#download' : 'https://github.com/HADIASSEMANI/text-to-speech-pdf-reader/releases/latest';
      link.querySelector('.download-label').textContent = fallback ? 'Get the app'
        : `Download for ${platform === 'windows' ? 'Windows' : 'macOS'}`;
    });

    const toggle = component.querySelector('.platform-toggle');
    toggle.hidden = !installer;
    toggle.textContent = choice === 'windows' ? 'Not on Windows? Get the macOS version'
      : 'Not on a Mac? Get the Windows version';

    const note = component.querySelector('.mac-note');
    note.hidden = choice !== 'macos';
    note.textContent = intelMac ? 'This build is for Apple silicon Macs. On an Intel Mac, run from source.'
      : 'Requires a Mac with Apple silicon (M1 or later).';

    const sourceLink = component.querySelector('.source-link');
    if (sourceLink) {
      sourceLink.classList.toggle('button', os === 'linux');
      sourceLink.classList.toggle('pill-cta', os === 'linux' && component.classList.contains('hero-download'));
    }
  });

  components.forEach((component) => {
    const toggle = component.querySelector('.platform-toggle');
    if (!toggle) return;
    toggle.addEventListener('click', () => {
      selected = selected === 'windows' ? 'macos' : 'windows';
      renderDownloads();
      const announcement = component.querySelector('.download-announcement');
      if (announcement) {
        announcement.textContent =
          `Download for ${selected === 'windows' ? 'Windows. Installer (.exe).' : 'macOS. Apple silicon (arm64), .dmg.'}`;
      }
    });
  });

  renderDownloads();

  if (os === 'macos' && navigator.userAgentData?.getHighEntropyValues) {
    navigator.userAgentData.getHighEntropyValues(['architecture']).then(({ architecture }) => {
      intelMac = architecture === 'x86';
      renderDownloads();
    }).catch(() => { /* Architecture hints are optional; keep the Apple silicon requirement. */ });
  }

  document.querySelectorAll('[data-panel]').forEach((panel) => {
    const recommended = panel.dataset.panel === os;
    panel.classList.toggle('is-recommended', recommended);
    if (recommended) {
      const tag = document.createElement('span');
      tag.className = 'recommended-tag';
      tag.textContent = 'Recommended for you';
      panel.prepend(tag);
      const btn = panel.querySelector('.button');
      if (btn) btn.classList.replace('secondary', 'primary');
    }
  });

  // Section 01: Real Audio Sample Player + Synchronized Cue Highlighting
  const audio = document.querySelector('#sample-audio');
  const playBtn = document.querySelector('#sample-play');
  const playIcon = document.querySelector('#sample-play-icon');
  const progressBar = document.querySelector('#sample-progress-bar');
  const progressFill = document.querySelector('#sample-progress-fill');
  const currentTimeEl = document.querySelector('#sample-current-time');
  const durationEl = document.querySelector('#sample-duration');
  const passageEl = document.querySelector('#sample-passage');

  let cueElements = [...document.querySelectorAll('.sample-cue')];
  let cues = cueElements.map((el) => ({
    start: +el.dataset.start,
    end: +el.dataset.end,
    text: el.textContent
  }));

  const formatTime = (seconds) => {
    const s = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return `${mins}:${String(secs).padStart(2, '0')}`;
  };

  const getDuration = () => {
    if (audio && Number.isFinite(audio.duration) && audio.duration > 0) {
      return audio.duration;
    }
    return cues.length ? cues[cues.length - 1].end : 0;
  };

  const buildCueSpans = (loadedCues) => {
    if (!passageEl || !Array.isArray(loadedCues) || !loadedCues.length) return;
    cues = loadedCues;
    passageEl.textContent = '';
    cueElements = cues.map((cue, index) => {
      const span = document.createElement('span');
      span.className = 'sample-cue';
      if (index === 0) span.classList.add('is-active');
      span.dataset.cueIndex = String(index);
      span.dataset.start = String(cue.start);
      span.dataset.end = String(cue.end);
      span.tabIndex = 0;
      span.setAttribute('role', 'button');
      span.textContent = cue.text;
      span.addEventListener('click', () => seekAndPlay(cue.start));
      span.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          seekAndPlay(cue.start);
        }
      });
      passageEl.appendChild(span);
      if (index < cues.length - 1) {
        passageEl.appendChild(document.createTextNode(' '));
      }
      return span;
    });
  };

  const updatePlayerUI = () => {
    if (!audio) return;
    const current = audio.currentTime || 0;
    const total = getDuration();
    const isPlaying = !audio.paused && !audio.ended;

    const pct = total > 0 ? Math.min(100, Math.max(0, (current / total) * 100)) : 0;
    if (progressFill) progressFill.style.width = `${pct.toFixed(2)}%`;
    if (currentTimeEl) currentTimeEl.textContent = formatTime(current);
    if (durationEl) durationEl.textContent = formatTime(total);

    if (progressBar) {
      progressBar.setAttribute('aria-valuemax', String(Math.round(total)));
      progressBar.setAttribute('aria-valuenow', String(Math.round(current)));
      progressBar.setAttribute('aria-valuetext', `${Math.round(current)} seconds of ${Math.round(total)} seconds`);
    }

    if (playBtn) {
      playBtn.setAttribute('aria-pressed', String(isPlaying));
      playBtn.setAttribute('aria-label', isPlaying ? 'Pause sample narration' : 'Play sample narration');
    }
    if (playIcon) {
      playIcon.setAttribute('d', isPlaying ? 'M7 5h3.5v14H7V5Zm6.5 0H17v14h-3.5V5Z' : 'm8 5 11 7-11 7Z');
    }

    let activeIdx = cues.findIndex((cue) => current >= cue.start && current < cue.end);
    if (activeIdx === -1) {
      activeIdx = cues.length && current >= cues[cues.length - 1].end ? cues.length - 1 : 0;
    }
    cueElements.forEach((el, idx) => {
      el.classList.toggle('is-active', idx === activeIdx);
    });
  };

  const seekTo = (targetSeconds) => {
    if (!audio) return;
    const total = getDuration();
    audio.currentTime = Math.max(0, Math.min(total, targetSeconds));
    updatePlayerUI();
  };

  const seekAndPlay = (targetSeconds) => {
    if (!audio) return;
    seekTo(targetSeconds);
    audio.play().catch(() => {});
  };

  // Wire initial static span events before JSON resolves
  cueElements.forEach((span) => {
    const start = parseFloat(span.dataset.start || '0');
    span.addEventListener('click', () => seekAndPlay(start));
    span.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        seekAndPlay(start);
      }
    });
  });

  fetch('assets/sample-cues.json')
    .then((res) => (res.ok ? res.json() : null))
    .then((data) => {
      if (Array.isArray(data) && data.length) {
        buildCueSpans(data);
        updatePlayerUI();
      }
    })
    .catch(() => { /* Keep inline fallback cues when offline or file:// */ });

  if (audio && playBtn) {
    playBtn.addEventListener('click', () => {
      if (audio.paused || audio.ended) {
        if (audio.ended) audio.currentTime = 0;
        audio.play().catch(() => {});
      } else {
        audio.pause();
      }
    });

    audio.addEventListener('loadedmetadata', updatePlayerUI);
    audio.addEventListener('timeupdate', updatePlayerUI);
    audio.addEventListener('play', updatePlayerUI);
    audio.addEventListener('pause', updatePlayerUI);
    audio.addEventListener('ended', updatePlayerUI);
  }

  if (progressBar && audio) {
    const seekFromPointer = (event) => {
      const rect = progressBar.getBoundingClientRect();
      if (!rect.width) return;
      const ratio = (event.clientX - rect.left) / rect.width;
      seekTo(ratio * getDuration());
    };

    let dragging = false;
    progressBar.addEventListener('pointerdown', (event) => {
      dragging = true;
      progressBar.setPointerCapture(event.pointerId);
      seekFromPointer(event);
    });
    progressBar.addEventListener('pointermove', (event) => {
      if (dragging) seekFromPointer(event);
    });
    const endDrag = (event) => {
      if (!dragging) return;
      dragging = false;
      if (progressBar.hasPointerCapture(event.pointerId)) {
        progressBar.releasePointerCapture(event.pointerId);
      }
    };
    progressBar.addEventListener('pointerup', endDrag);
    progressBar.addEventListener('pointercancel', endDrag);

    progressBar.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        seekTo((audio.currentTime || 0) + 2);
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        seekTo((audio.currentTime || 0) - 2);
      } else if (event.key === 'Home') {
        event.preventDefault();
        seekTo(0);
      } else if (event.key === 'End') {
        event.preventDefault();
        seekTo(getDuration());
      }
    });
  }

  updatePlayerUI();

  // Sticky Header & Active Section Highlighting
  const header = document.querySelector('.site-header');
  const sections = [...document.querySelectorAll('main > section[id]')];
  const navLinks = [...document.querySelectorAll('.site-header nav a[href^="#"]')];

  const updateNavigation = () => {
    if (!header) return;
    header.classList.toggle('is-scrolled', window.scrollY > 16);
    const current = sections.filter((section) => section.getBoundingClientRect().top <= header.offsetHeight + 100).pop();
    navLinks.forEach((link) => {
      if (current && link.hash === `#${current.id}`) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
  };

  let scrollFrame = 0;
  window.addEventListener('scroll', () => {
    if (!scrollFrame) {
      scrollFrame = requestAnimationFrame(() => {
        updateNavigation();
        scrollFrame = 0;
      });
    }
  }, { passive: true });
  window.addEventListener('resize', updateNavigation);
  updateNavigation();
})();

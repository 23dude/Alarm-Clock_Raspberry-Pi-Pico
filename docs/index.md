---
title: "FSM Alarm Clock"
description: "SYSEN 5412 Final Project — Yi-Chia Wu (yw2839)"
---

<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
  mermaid.initialize({ startOnLoad: false, theme: 'default' });
  document.querySelectorAll('pre > code.language-mermaid').forEach((el) => {
    const div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = el.textContent;
    el.parentElement.replaceWith(div);
  });
  await mermaid.run({ querySelector: '.mermaid' });
</script>

<script type="module">
  // Auto-build sticky top nav from h2 headings
  const headings = document.querySelectorAll('.main-content h2');
  if (headings.length) {
    const nav = document.createElement('nav');
    nav.className = 'top-nav';
    const inner = document.createElement('div');
    inner.className = 'top-nav-inner';
    nav.appendChild(inner);

    const brand = document.createElement('a');
    brand.className = 'top-nav-brand';
    brand.href = '#';
    brand.textContent = 'FSM Clock';
    inner.appendChild(brand);

    const items = [];
    headings.forEach((h) => {
      if (!h.id) {
        h.id = h.textContent.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
      }
      const link = document.createElement('a');
      link.href = `#${h.id}`;
      link.textContent = h.textContent;
      link.className = 'top-nav-item';
      inner.appendChild(link);
      items.push(link);
    });

    document.body.insertBefore(nav, document.body.firstChild);

    function setActive(id) {
      items.forEach((l) => l.classList.toggle('active', l.getAttribute('href') === `#${id}`));
    }

    inner.addEventListener('click', (e) => {
      const link = e.target.closest('.top-nav-item');
      if (link) setActive(link.getAttribute('href').slice(1));
    });

    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((e) => e.isIntersecting);
      if (!visible.length) return;
      const topMost = visible.reduce((a, b) =>
        a.boundingClientRect.top < b.boundingClientRect.top ? a : b
      );
      setActive(topMost.target.id);
    }, { rootMargin: '-10% 0px -75% 0px', threshold: 0 });

    headings.forEach((h) => observer.observe(h));
  }
</script>

# FSM Alarm Clock

## Introduction

*(Coming soon)*

## Demo Video

<div class="video-short">
  <div class="video-short-inner">
    <iframe
      src="https://www.youtube.com/embed/g99llM1LRGQ"
      title="FSM Alarm Clock Demo"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
      allowfullscreen>
    </iframe>
  </div>
</div>

## System Overview

*(Coming soon)*

## Hardware

*(Coming soon)*

## FSM Design

*(Coming soon)*

## Key Challenges

*(Coming soon)*

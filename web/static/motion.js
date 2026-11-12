// Movimiento que el CSS no puede hacer solo. Reparto: el CSS (style.css) lleva hover, pulsación y estados;
// aquí van las secuencias, FLIP (bloques que cambian de sitio al repintarse su columna) y los contadores,
// con GSAP + Flip (static/vendor). Las plantillas lo usan a través de window.Motion y funcionan igual sin él.
// Con «reducir movimiento» no hay desplazamientos, escalas ni confeti: fundidos de 150 ms y números que saltan.
(function () {
  "use strict";
  var gsap = window.gsap, Flip = window.Flip, body = document.body;
  var Motion = window.Motion = {
    reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,
    quiet: !!window.arrivedByKeyboard,   // se llegó con un atajo de teclado: la página no hace su entrada
  };

  // Vuelve a lanzar una animación CSS de un solo uso (clase que se quita sola al terminar)
  Motion.replay = function (el, cls, ms) {
    if (!el) return;
    clearTimeout(el["_" + cls]);
    el.classList.remove(cls);
    void el.offsetWidth;
    el.classList.add(cls);
    el["_" + cls] = setTimeout(function () { el.classList.remove(cls); }, ms || 600);
  };

  if (!gsap || !Flip) return;
  gsap.registerPlugin(Flip);
  gsap.matchMedia().add(
    { reduce: "(prefers-reduced-motion: reduce)", full: "(prefers-reduced-motion: no-preference)" },
    function (ctx) { Motion.reduced = !!ctx.conditions.reduce; }
  );

  var list = function (root, sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); };
  // GSAP deja estilos en línea (y pasa translate/rotate/scale a «none»): al acabar no queda ni rastro,
  // para que las clases de estado (arrastre, pulsación) sigan mandando
  var PROPS = ["transform", "translate", "rotate", "scale", "opacity", "transform-origin", "transition"];
  // Mientras GSAP mueve algo, su transición CSS de transform se aparta (si no, iría siempre un paso por detrás)
  function hold(els) {
    els.forEach(function (el) { el.style.transition = "none"; });
    return els;
  }
  function tidy(els) {
    els.forEach(function (el) {
      PROPS.forEach(function (p) { el.style.removeProperty(p); });
      list(el, ".ts-title, .ts-meta").forEach(function (kid) {
        kid.style.removeProperty("transform");
        kid.style.removeProperty("opacity");
      });
    });
  }

  // ---- Parte de horas: los bloques de una columna que se repinta (editar, añadir, borrar, deshacer) ----
  // La columna entera llega nueva del servidor. Cada bloque lleva un data-flip-id (título + nº de aparición);
  // se guarda dónde estaba cada uno antes del cambio y, ya con la columna nueva, Flip lleva cada bloque de su
  // sitio anterior al nuevo. Los que no estaban entran con un pequeño rebote.
  var blocksOf = function (day) { return list(day, ".ts-block[data-title]:not([data-gone])"); };
  function tag(day) {
    var seen = {};
    blocksOf(day).forEach(function (b) {
      var title = b.dataset.title;
      seen[title] = (seen[title] || 0) + 1;
      b.dataset.flipId = day.id + "|" + title + "#" + seen[title];
    });
  }

  // timesheet.html avisa de qué bloque está cambiando: { from: bloque de partida, to: {title, start, end},
  // drop: se acaba de soltar tras arrastrarlo, leave: bloque que se borra }
  var expected = {}, pending = {};
  Motion.expect = function (dayId, hint) {
    if (hint) expected[dayId] = hint; else delete expected[dayId];
  };
  Motion.touched = null;   // el bloque recién guardado (el formulario vuelve a él al cerrarse)

  body.addEventListener("htmx:beforeSwap", function (e) {
    var day = e.detail.target;
    if (!day || !day.classList || !day.classList.contains("ts-day") || !e.detail.shouldSwap) return;
    var blocks = blocksOf(day), snap = pending[day.id] = { minutes: day.dataset.minutes, state: null, rects: {} };
    if (!blocks.length) return;
    tag(day);
    blocks.forEach(function (b) { snap.rects[b.dataset.flipId] = b.getBoundingClientRect(); });
    snap.state = Flip.getState(blocks, { simple: true });
    // Lo que estuviera a medias en los bloques que se van, se corta aquí: los nuevos salen de donde iban
    Flip.killFlipsOf(blocks);
    gsap.killTweensOf(blocks);
    var week = day.closest(".ts-week");
    if (week) week.classList.add("is-flipping");   // la columna no hace además su fundido de llegada
  });

  body.addEventListener("htmx:afterSwap", function (e) {
    var old = e.detail.target, snap = old && old.id && pending[old.id];
    if (!snap) return;
    delete pending[old.id];
    var hint = expected[old.id], day = document.getElementById(old.id);
    delete expected[old.id];
    if (!day || day === old) return;
    if (snap.state && !day.classList.contains("just-generated")) flipBlocks(day, snap, hint);
  });
  body.addEventListener("htmx:afterSettle", function () {
    list(document, ".ts-week.is-flipping").forEach(function (w) { w.classList.remove("is-flipping"); });
  });

  function flipBlocks(day, snap, hint) {
    tag(day);
    var blocks = blocksOf(day), dropped = null;
    if (hint && hint.to) {
      var to = hint.to, target = blocks.filter(function (b) {
        return b.dataset.title === to.title && Number(b.dataset.start) === to.start && Number(b.dataset.end) === to.end;
      })[0];
      var fromId = hint.from && hint.from.dataset.flipId;
      if (target) {
        Motion.touched = target;
        // Aunque le hayan cambiado el título, es el mismo bloque: hereda el id del de partida
        if (fromId && target.dataset.flipId !== fromId) {
          var twin = blocks.filter(function (b) { return b.dataset.flipId === fromId; })[0];
          if (twin) twin.dataset.flipId = target.dataset.flipId;
          target.dataset.flipId = fromId;
        }
        if (hint.drop) dropped = target;
      }
    }
    // Recién soltado tras arrastrarlo: ya está en su sitio, solo le queda posarse (style.css)
    if (dropped) Motion.replay(dropped, "is-settling", 420);

    var entering = [], moving = [], resized = [];
    blocks.forEach(function (b) {
      if (b === dropped) return;
      var was = snap.rects[b.dataset.flipId], now = b.getBoundingClientRect();
      if (!was) return entering.push(b);
      var grew = Math.abs(was.width - now.width) > 0.5 || Math.abs(was.height - now.height) > 0.5;
      if (grew || Math.abs(was.left - now.left) > 0.5 || Math.abs(was.top - now.top) > 0.5) moving.push(b);
      if (grew) resized.push(b);
    });
    if (!entering.length && !moving.length) return;
    if (Motion.reduced) {
      return gsap.fromTo(hold(entering.concat(moving)), { opacity: 0 },
        { opacity: 1, duration: 0.15, ease: "none", onComplete: function () { tidy(entering.concat(moving)); } });
    }
    // Con el formulario aún cerrándose encima, los bloques esperan un instante para que se les vea llegar
    var delay = document.querySelector("#task-dialog[open]") ? 0.1 : 0;
    if (moving.length) {
      Flip.from(snap.state, {
        targets: hold(moving), duration: 0.4, ease: "power3.inOut", delay: delay, scale: true, simple: true,
        // Un bloque que cambia de duración se escala: su texto lleva la escala inversa y no se deforma
        // (y el horario, que se amontonaría con el título mientras el bloque está encogido, espera a caber)
        onUpdate: function () {
          resized.forEach(function (b) {
            var sx = Number(gsap.getProperty(b, "scaleX")) || 1, sy = Number(gsap.getProperty(b, "scaleY")) || 1;
            var fit = Math.min(sy, 1 / sy);
            list(b, ".ts-title, .ts-meta").forEach(function (kid) {
              kid.style.transform = "scale(" + 1 / sx + "," + 1 / sy + ")";
              if (kid.classList.contains("ts-meta")) kid.style.opacity = Math.max(0, Math.min(1, (fit - 0.6) / 0.3));
            });
          });
        },
        onComplete: function () { tidy(moving); },
      });
    }
    var gaps = entering.filter(function (b) { return b.classList.contains("is-empty"); });
    var fresh = entering.filter(function (b) { return !b.classList.contains("is-empty"); });
    if (fresh.length) {
      gsap.fromTo(hold(fresh), { scale: 0.85, opacity: 0 }, {
        scale: 1, opacity: 1, duration: 0.32, ease: "back.out(2.2)", delay: delay, stagger: 0.03,
        onComplete: function () { tidy(fresh); },
      });
    }
    if (gaps.length) {   // los huecos «Por definir» no son protagonistas: solo aparecen
      gsap.fromTo(hold(gaps), { opacity: 0 },
        { opacity: 1, duration: 0.2, ease: "none", delay: delay, onComplete: function () { tidy(gaps); } });
    }
  }

  // El bloque que se borra se encoge antes de pedir el cambio; si el servidor no lo acepta, vuelve
  Motion.leave = function (el) {
    return new Promise(function (resolve) {
      el.setAttribute("data-gone", "");
      gsap.to(hold([el]), Motion.reduced
        ? { opacity: 0, duration: 0.15, ease: "none", overwrite: true, onComplete: resolve }
        : { scale: 0.9, opacity: 0, duration: 0.18, ease: "power2.out", overwrite: true, onComplete: resolve });
    });
  };
  Motion.restore = function (el) {
    gsap.killTweensOf(el);
    el.removeAttribute("data-gone");
    tidy([el]);
  };

  // Un bloque que cambia de sitio sin repintarse (el arrastre que no se llega a guardar): se desliza hasta él
  Motion.glide = function (el, change) {
    if (Motion.reduced) return change();
    var state = Flip.getState(el, { simple: true });
    change();
    hold([el]);
    Flip.from(state, { duration: 0.38, ease: "power3.inOut", scale: true, simple: true,
                       onComplete: function () { tidy([el]); } });
  };
})();

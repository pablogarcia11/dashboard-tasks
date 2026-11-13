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

  // La página acaba de abrirse: lo que llega en este rato es su entrada, no un cambio (los totales cuentan
  // desde cero una vez, sin salto final). Con atajo de teclado no hay entrada
  var fresh = true, arriving = !Motion.quiet;
  setTimeout(function () { fresh = arriving = false; }, 1600);

  var list = function (root, sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); };
  // GSAP deja estilos en línea (y pasa translate/rotate/scale a «none»): al acabar no queda ni rastro,
  // para que las clases de estado (arrastre, pulsación) sigan mandando
  var PROPS = ["transform", "translate", "rotate", "scale", "opacity", "transform-origin", "transition",
               "stroke-dashoffset"];
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
  var expected = {}, pending = {}, marks = {};
  // Clases y variables que se ponen en la columna nueva: HTMX las borra al asentarla (le repone los atributos
  // que traía del servidor), así que se vuelven a poner en ese mismo instante
  function mark(day, fn) {
    marks[day.id] = fn;
    fn(day);
  }
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
    if (!snap) {
      if (old && /^ts-\d/.test(old.id || "")) enter(old.id);   // la columna llega por primera vez
      return;
    }
    delete pending[old.id];
    var hint = expected[old.id], day = document.getElementById(old.id);
    delete expected[old.id];
    if (!day || day === old) return;
    if (day.classList.contains("just-generated")) wave(day);
    else if (snap.state) flipBlocks(day, snap, hint);
    // El total del día (al pie de la columna) viene ya escrito: si ha cambiado, rueda desde el anterior
    var foot = day.querySelector(".ts-foot strong");
    if (foot && day.dataset.minutes !== undefined && day.dataset.minutes !== snap.minutes) {
      Motion.count(foot, Number(snap.minutes) || 0, Number(day.dataset.minutes), foot.textContent);
    }
  });
  body.addEventListener("htmx:afterSettle", function (e) {
    list(document, ".ts-week.is-flipping").forEach(function (w) { w.classList.remove("is-flipping"); });
    var id = e.detail.target && e.detail.target.id, day = id && marks[id] && document.getElementById(id);
    if (day) marks[id](day);
    if (id) delete marks[id];
  });

  // Al abrir la semana, las columnas entran una tras otra, de izquierda a derecha, lleguen en el orden que
  // lleguen (cada una pide sus datos por su cuenta). La animación es CSS (clase col-enter)
  var firstColumn = 0;
  function enter(id) {
    var day = document.getElementById(id);
    // (recién insertada aún no lleva sus clases: HTMX se las pone al asentarla, y ahí arranca la animación)
    if (!arriving || Motion.reduced || !day || !day.querySelector(".ts-grid")) return;
    var now = performance.now(), columns = list(day.parentNode, ":scope > div[id^='ts-']");
    firstColumn = firstColumn || now;
    var delay = Math.max(0, firstColumn + columns.indexOf(day) * 60 - now);
    mark(day, function (el) {
      el.classList.add("col-enter");
      el.style.setProperty("--col-delay", delay + "ms");
    });
  }

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

  // «Generar»: los bloques caen en oleada (la animación es CSS, clase just-generated; aquí solo se reparte
  // el tiempo). Las columnas de «Generar semana» que llegan a la vez salen con 60 ms entre una y otra
  var waveFree = 0;
  Motion.countAfter = 0;   // hasta cuándo esperan los totales para empezar a contar
  function wave(day) {
    var n = blocksOf(day).length, now = performance.now();
    var step = n > 1 ? Math.min(35, 400 / (n - 1)) : 0, delay = Math.max(0, waveFree - now);
    waveFree = now + delay + 60;
    mark(day, function (el) {
      el.style.setProperty("--wave-step", step + "ms");
      el.style.setProperty("--wave-delay", delay + "ms");
    });
    var total = delay + step * (n - 1) + 380;
    if (!Motion.reduced) Motion.countAfter = Math.max(Motion.countAfter, now + total - 160);
    // Hecha la oleada, la clase se va: si se quedara, cualquier otra animación del bloque la relanzaría al acabar
    setTimeout(function () {
      day.classList.remove("just-generated");
      day.style.removeProperty("--wave-step");
      day.style.removeProperty("--wave-delay");
    }, Math.max(total, 700) + 80);
  }

  // ---- Totales (semana, día, categoría): ruedan hasta el valor nuevo en pasos de 15 min ----
  // El total no cambia de ancho mientras rueda (el de la semana está en la cabecera y, al ensancharse, mandaría
  // los botones a otra línea a mitad de la cuenta): reserva el ancho del más largo de sus dos extremos y escribe
  // siempre horas y minutos, o solo horas, de una en una, si los dos extremos son horas en punto
  function clock(minutes) {
    var m = Math.round(minutes), rest = m % 60;
    return Math.floor(m / 60) + " h " + (rest < 10 ? "0" : "") + rest + " min";
  }
  // from: valor anterior (undefined si es la primera vez que se escribe); text: cómo se lee el valor final
  Motion.count = function (el, from, to, text) {
    var running = el._count && el._count.tween.isActive() ? el._count : null, intro = false;
    if (running) { from = running.v; running.tween.kill(); }
    if (from === undefined && arriving && to) { from = 0; intro = true; }
    if (Motion.reduced || from === undefined || from === to) {
      el.textContent = text;
      el.style.minWidth = "";
      return true;
    }
    var o = el._count = { v: from };
    var whole = from % 60 === 0 && to % 60 === 0 && text.indexOf("min") === -1;
    var show = whole ? function (m) { return Math.round(m / 60) + " h"; } : clock;
    var width = el.offsetWidth;
    el.textContent = text;
    el.style.minWidth = Math.max(width, el.offsetWidth) + "px";
    el.textContent = show(from);
    o.tween = gsap.to(o, {
      v: to, duration: 0.6, ease: "power3.out", snap: { v: whole ? 60 : 15 },
      delay: Math.max(0, Motion.countAfter - performance.now()) / 1000,
      onUpdate: function () {
        var now = show(o.v);
        if (now !== el.textContent) el.textContent = now;
      },
      onComplete: function () {
        el.textContent = text;
        el.style.minWidth = "";
        if (!intro && !arriving) Motion.replay(el, "is-popped", 300);
      },
    });
    return true;
  };

  // ---- Jornada completa: el número del día toma impulso y salta, se abre un aro y se dibuja la marca ----
  // Espera a que el total termine de contar. week: además, confeti desde el total de la semana.
  // Devuelve si ha lanzado el confeti (timesheet.html lo recuerda: una vez por semana)
  Motion.celebrate = function (heads, week) {
    if (Motion.reduced) return false;            // la marca aparece con su fundido (CSS) y nada más
    if (fresh && Motion.quiet) week = false;     // se llegó con el teclado: la página no hace entrada
    var wait = Math.max(0, Motion.countAfter - performance.now()) / 1000 + (fresh ? 0.7 : 0.45);
    heads.forEach(function (head, i) {
      var num = head.querySelector("strong"), ring = head.querySelector(".day-ring");
      var badge = head.querySelector(".day-done"), path = badge.querySelector("path"), all = [num, ring, badge, path];
      gsap.killTweensOf(all);
      hold(all);
      gsap.timeline({ delay: wait + i * 0.08, onComplete: function () { tidy(all); } })
        .to(num, { keyframes: [{ scale: 0.82, duration: 0.12, ease: "power2.in" },
                               { scale: 1, duration: 0.45, ease: "back.out(2)" }] }, 0)
        .fromTo(ring, { scale: 1, opacity: 0.8 },
                { scale: 2.4, opacity: 0, duration: 0.6, ease: "power2.out", immediateRender: false }, 0.12)
        .fromTo(badge, { scale: 0.4, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: "back.out(2.4)" }, 0.2)
        .fromTo(path, { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.26, ease: "power2.out" }, 0.3);
    });
    if (week) gsap.delayedCall(wait + (heads.length ? 0.5 : 0), burst, [heads]);
    return !!week;
  };

  // Sale del total de la semana; si queda fuera de la vista (se está abajo, en la rejilla), del total del día
  // que acaba de completarse
  function burst(heads) {
    var onScreen = function (el) {
      var r = el && el.getBoundingClientRect();
      return r && r.width && r.top > 0 && r.bottom < innerHeight;
    };
    var feet = heads.map(function (h) { return document.querySelector("#ts-" + h.id.slice(8) + " .ts-foot strong"); });
    var src = [document.getElementById("week-total")].concat(feet, list(document, ".ts-foot strong")).filter(onScreen)[0];
    if (!src || Motion.reduced) return;
    var r = src.getBoundingClientRect(), box = document.createElement("div"), random = gsap.utils.random;
    box.className = "burst";
    box.setAttribute("aria-hidden", "true");
    box.style.left = r.left + r.width / 2 + "px";
    box.style.top = r.top + r.height / 2 + "px";
    ["dev", "doc", "meet", "admin", "learn"].forEach(function (cat, c) {
      for (var k = 0; k < (c < 1 ? 4 : 3); k++) {   // 16 piezas
        var bit = document.createElement("i");
        bit.style.background = "var(--" + cat + "-line)";
        if (k === 1) bit.className = "is-round";
        box.appendChild(bit);
        var up = random(34, 96), time = random(0.75, 0.9);
        gsap.timeline()
          .to(bit, { x: random(-120, 120), rotation: random(-420, 420), duration: time, ease: "power2.out" }, 0)
          .to(bit, { y: -up, duration: time * 0.4, ease: "power2.out" }, 0)
          .to(bit, { y: random(10, 60), duration: time * 0.6, ease: "power2.in" }, time * 0.4)
          .to(bit, { opacity: 0, scale: 0.5, duration: time * 0.35, ease: "power1.in" }, time * 0.65);
      }
    });
    body.appendChild(box);
    Motion.replay(src, "is-popped", 300);
    gsap.delayedCall(1, function () { box.remove(); });
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
    if (Motion.reduced) { change(); return true; }
    var state = Flip.getState(el, { simple: true });
    change();
    hold([el]);
    Flip.from(state, { duration: 0.38, ease: "power3.inOut", scale: true, simple: true,
                       onComplete: function () { tidy([el]); } });
    return true;
  };
})();

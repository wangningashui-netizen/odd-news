(function () {
  "use strict";

  var PAGE = 18;
  var WEEK = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"];
  var REGION_ORDER = ["", "全球", "印度", "英国", "美国", "日本", "爱尔兰"];

  var dateSelect = document.getElementById("date-select");
  var olderBtn = document.getElementById("older-day");
  var newerBtn = document.getElementById("newer-day");
  var regionsEl = document.getElementById("regions");
  var sourceEl = document.getElementById("source");
  var searchEl = document.getElementById("search");
  var statusEl = document.getElementById("status");
  var headingEl = document.getElementById("day-heading");
  var gridEl = document.getElementById("grid");
  var emptyEl = document.getElementById("empty");
  var moreEl = document.getElementById("more");
  var sentinelEl = document.getElementById("sentinel");
  var lightboxEl = document.getElementById("lightbox");
  var lightboxImg = document.getElementById("lightbox-img");
  var lightboxCaption = document.getElementById("lightbox-caption");

  var indexDates = [];
  var currentDate = "";
  var items = [];
  var filtered = [];
  var shown = 0;
  var activeRegion = "";
  var cache = Object.create(null);

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function safeHttp(url) {
    if (!url) return "";
    try {
      var parsed = new URL(url, window.location.href);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.href;
    } catch (err) {
      return "";
    }
    return "";
  }

  function formatDay(iso) {
    var parts = iso.split("-");
    if (parts.length < 3) return iso;
    var year = Number(parts[0]);
    var month = Number(parts[1]);
    var day = Number(parts[2]);
    var date = new Date(Date.UTC(year, month - 1, day));
    return year + "年" + month + "月" + day + "日 " + WEEK[date.getUTCDay()];
  }

  function formatTime(iso) {
    if (!iso) return "";
    var match = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!match) return iso;
    return Number(match[2]) + "月" + Number(match[3]) + "日 " + match[4] + ":" + match[5];
  }

  function haystack(item) {
    return [item.title_zh, item.title_en, item.summary_zh, item.summary_en]
      .filter(Boolean)
      .join("\n")
      .toLowerCase();
  }

  function applyFilters() {
    var query = searchEl.value.trim().toLowerCase();
    var source = sourceEl.value;
    filtered = items.filter(function (item) {
      if (source && item.source !== source) return false;
      if (activeRegion && item.region !== activeRegion) return false;
      if (query && haystack(item).indexOf(query) === -1) return false;
      return true;
    });
    shown = 0;
    gridEl.replaceChildren();
    appendMore();
  }

  function updateStatus() {
    var total = items.length;
    var matched = filtered.length;
    if (!currentDate) {
      statusEl.textContent = "没有可读的日期。";
      return;
    }
    if (!total) {
      statusEl.textContent = "这一天还没有条目。";
      return;
    }
    var visible = Math.min(shown, matched);
    statusEl.textContent = "这一天 " + total + " 条，当前显示 " + visible + " / " + matched + " 条。";
  }

  function placeholderSrc() {
    return "assets/placeholder.svg";
  }

  function openLightbox(src, caption) {
    lightboxImg.src = src;
    lightboxImg.alt = caption || "主图";
    lightboxCaption.textContent = caption || "";
    lightboxEl.hidden = false;
    document.body.style.overflow = "hidden";
    document.getElementById("lightbox-close").focus();
  }

  function closeLightbox() {
    lightboxEl.hidden = true;
    lightboxImg.removeAttribute("src");
    document.body.style.overflow = "";
  }

  function makeCard(item, hero) {
    var card = el("article", hero ? "card hero" : "card");
    var imageUrl = safeHttp(item.image);
    var title = item.title_zh || item.title_en || "无标题";
    var thumb = el("button", "thumb" + (imageUrl ? " can-zoom" : ""));
    thumb.type = "button";
    thumb.setAttribute("aria-label", imageUrl ? "查看大图：" + title : "暂无主图");
    var img = document.createElement("img");
    img.alt = title;
    img.referrerPolicy = "no-referrer";
    img.loading = "lazy";
    img.decoding = "async";
    img.width = 640;
    img.height = 360;
    if (imageUrl) {
      img.src = imageUrl;
      img.addEventListener("error", function () {
        if (img.dataset.failed === "1") return;
        img.dataset.failed = "1";
        img.src = placeholderSrc();
        img.alt = "图片无法加载";
        thumb.classList.remove("can-zoom");
      });
      thumb.addEventListener("click", function () {
        if (img.dataset.failed === "1") return;
        openLightbox(imageUrl, title);
      });
    } else {
      img.src = placeholderSrc();
      img.alt = "暂无主图";
      thumb.disabled = true;
    }
    thumb.appendChild(img);

    var body = el("div", "card-body");
    var meta = el("div", "meta");
    var region = el("span", "badge region", item.region || "全球");
    region.setAttribute("data-region", item.region || "全球");
    meta.appendChild(region);
    meta.appendChild(el("span", "badge", item.source || "未知来源"));
    if (item.translation_status === "pending" || !item.title_zh) {
      meta.appendChild(el("span", "badge warn", "待翻译"));
    } else if (item.translation_status === "fallback") {
      meta.appendChild(el("span", "badge warn", "机翻"));
    }
    var time = document.createElement("time");
    time.dateTime = item.published_at || "";
    time.textContent = formatTime(item.published_at);
    meta.appendChild(time);

    var heading = el("h3", null, title);
    body.appendChild(meta);
    body.appendChild(heading);
    if (item.title_zh && item.title_en) {
      var en = el("p", "title-en", item.title_en);
      en.lang = "en";
      body.appendChild(en);
    }
    var summaryText = item.summary_zh || item.summary_en || "";
    if (summaryText && summaryText !== title) {
      var summary = el("p", "summary");
      var label = el("span", "summary-label", "概要");
      summary.appendChild(label);
      summary.appendChild(document.createTextNode(summaryText));
      body.appendChild(summary);
    }
    var link = safeHttp(item.url);
    if (link) {
      var anchor = el("a", "read", "阅读原文");
      anchor.href = link;
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      body.appendChild(anchor);
    }
    card.appendChild(thumb);
    card.appendChild(body);
    return card;
  }

  function appendMore() {
    var unfiltered = !searchEl.value.trim() && !sourceEl.value && !activeRegion;
    var next = filtered.slice(shown, shown + PAGE);
    next.forEach(function (item, index) {
      var hero = unfiltered && shown === 0 && index === 0;
      gridEl.appendChild(makeCard(item, hero));
    });
    shown += next.length;
    var done = shown >= filtered.length;
    moreEl.hidden = done || filtered.length === 0;
    emptyEl.hidden = filtered.length !== 0;
    sentinelEl.hidden = done;
    updateStatus();
  }

  function fillSources() {
    var previous = sourceEl.value;
    var names = [];
    var seen = Object.create(null);
    items.forEach(function (item) {
      if (item.source && !seen[item.source]) {
        seen[item.source] = true;
        names.push(item.source);
      }
    });
    names.sort();
    sourceEl.replaceChildren(new Option("全部来源", ""));
    names.forEach(function (name) {
      sourceEl.appendChild(new Option(name, name));
    });
    if (seen[previous]) sourceEl.value = previous;
  }

  function renderRegions() {
    var present = Object.create(null);
    items.forEach(function (item) {
      if (item.region) present[item.region] = true;
    });
    var regions = REGION_ORDER.filter(function (name) {
      return name === "" || present[name];
    });
    Object.keys(present).forEach(function (name) {
      if (regions.indexOf(name) === -1) regions.push(name);
    });
    regionsEl.replaceChildren();
    regions.forEach(function (name) {
      var button = el("button", null, name || "全部地区");
      button.type = "button";
      button.setAttribute("aria-pressed", String((name || "") === activeRegion));
      button.addEventListener("click", function () {
        activeRegion = name;
        renderRegions();
        applyFilters();
      });
      regionsEl.appendChild(button);
    });
  }

  function dateIndex(date) {
    for (var i = 0; i < indexDates.length; i += 1) {
      if (indexDates[i].date === date) return i;
    }
    return -1;
  }

  function renderDates() {
    dateSelect.replaceChildren();
    indexDates.forEach(function (entry) {
      dateSelect.appendChild(new Option(formatDay(entry.date) + " · " + entry.count + "条", entry.date));
    });
    if (currentDate) dateSelect.value = currentDate;
    var index = dateIndex(currentDate);
    olderBtn.disabled = index < 0 || index >= indexDates.length - 1;
    newerBtn.disabled = index <= 0;
  }

  function selectDate(date, updateHash) {
    currentDate = date;
    if (updateHash) {
      history.replaceState(null, "", "#" + date);
    }
    headingEl.textContent = formatDay(date);
    renderDates();
    statusEl.textContent = "正在加载这一天…";
    loadDay(date).then(function (dayItems) {
      if (currentDate !== date) return;
      items = dayItems;
      fillSources();
      if (activeRegion && !items.some(function (item) { return item.region === activeRegion; })) {
        activeRegion = "";
      }
      renderRegions();
      applyFilters();
    }).catch(function () {
      if (currentDate !== date) return;
      items = [];
      filtered = [];
      gridEl.replaceChildren();
      emptyEl.hidden = false;
      emptyEl.textContent = "这一天的数据暂时读不出来。";
      statusEl.textContent = "加载失败。";
    });
  }

  function loadDay(date) {
    if (cache[date]) return Promise.resolve(cache[date]);
    return fetch("data/" + date + ".json", { cache: "no-cache" }).then(function (response) {
      if (!response.ok) throw new Error("day");
      return response.json();
    }).then(function (payload) {
      var list = (payload && payload.items) || [];
      list.sort(function (a, b) {
        return String(b.published_at || "").localeCompare(String(a.published_at || ""));
      });
      cache[date] = list;
      return list;
    });
  }

  function boot(index) {
    indexDates = (index && index.dates) || [];
    if (!indexDates.length) {
      statusEl.textContent = "还没有数据。每日任务跑过之后，这里会列出各天的条目。";
      headingEl.textContent = "尚无日报";
      return;
    }
    var hash = (location.hash || "").replace(/^#/, "");
    var known = indexDates.some(function (entry) { return entry.date === hash; });
    selectDate(known ? hash : indexDates[0].date, false);
  }

  dateSelect.addEventListener("change", function () {
    if (dateSelect.value && dateSelect.value !== currentDate) selectDate(dateSelect.value, true);
  });
  olderBtn.addEventListener("click", function () {
    var index = dateIndex(currentDate);
    if (index >= 0 && index < indexDates.length - 1) selectDate(indexDates[index + 1].date, true);
  });
  newerBtn.addEventListener("click", function () {
    var index = dateIndex(currentDate);
    if (index > 0) selectDate(indexDates[index - 1].date, true);
  });
  searchEl.addEventListener("input", function () {
    window.clearTimeout(searchEl._timer);
    searchEl._timer = window.setTimeout(applyFilters, 160);
  });
  sourceEl.addEventListener("change", applyFilters);
  moreEl.addEventListener("click", appendMore);
  document.getElementById("lightbox-close").addEventListener("click", closeLightbox);
  document.getElementById("lightbox-backdrop").addEventListener("click", closeLightbox);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeLightbox();
  });

  if ("IntersectionObserver" in window) {
    var observer = new IntersectionObserver(function (entries) {
      if (entries.some(function (entry) { return entry.isIntersecting; })) {
        if (shown < filtered.length) appendMore();
      }
    }, { rootMargin: "600px 0px" });
    observer.observe(sentinelEl);
  }

  window.addEventListener("hashchange", function () {
    var hash = (location.hash || "").replace(/^#/, "");
    if (hash && hash !== currentDate && indexDates.some(function (entry) { return entry.date === hash; })) {
      selectDate(hash, false);
    }
  });

  fetch("data/index.json", { cache: "no-cache" })
    .then(function (response) {
      if (!response.ok) throw new Error("index");
      return response.json();
    })
    .then(boot)
    .catch(function () {
      statusEl.textContent = "读不到 data/index.json。";
    });
})();

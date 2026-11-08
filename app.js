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
  var topicsEl = document.getElementById("topics");
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

  var FALLBACK_TAGS = ["街头食物", "卫生环境", "交通火车", "航空出行", "诈骗骗局", "影视神剧", "婚俗宗教", "商业套路", "科技发明", "军事政治", "动物", "犯罪法律", "奇人奇事", "科学发现", "历史考古", "健康医疗", "其他"];
  var indexDates = [];
  var tagOrder = FALLBACK_TAGS.slice();
  var allItems = [];
  var scopeDate = "";
  var filtered = [];
  var shown = 0;
  var activeRegion = "";
  var activeTags = [];

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

  function scopedItems() {
    if (!scopeDate) return allItems;
    return allItems.filter(function (item) { return item.date === scopeDate; });
  }

  function baseFiltered() {
    var query = searchEl.value.trim().toLowerCase();
    var source = sourceEl.value;
    return scopedItems().filter(function (item) {
      if (source && item.source !== source) return false;
      if (activeRegion && item.region !== activeRegion) return false;
      if (query && haystack(item).indexOf(query) === -1) return false;
      return true;
    });
  }

  function applyFilters() {
    var base = baseFiltered();
    filtered = base.filter(function (item) {
      if (!activeTags.length) return true;
      var tags = item.tags || [];
      return activeTags.some(function (tag) { return tags.indexOf(tag) !== -1; });
    });
    shown = 0;
    gridEl.replaceChildren();
    renderTags(base);
    appendMore();
  }

  function updateStatus() {
    var pool = scopedItems().length;
    var matched = filtered.length;
    var visible = Math.min(shown, matched);
    var where = scopeDate ? "这一天 " + pool + " 条" : "全部日期 " + pool + " 条";
    if (!allItems.length) {
      statusEl.textContent = "还没有可读的条目。";
      return;
    }
    statusEl.textContent = where + "，当前显示 " + visible + " / " + matched + " 条。";
  }

  function toggleTag(tag) {
    var index = activeTags.indexOf(tag);
    if (index === -1) activeTags.push(tag);
    else activeTags.splice(index, 1);
    applyFilters();
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

    var tagRow = el("div", "topic-tags");
    (item.tags || []).forEach(function (tag) {
      var chip = el("button", "topic", tag);
      chip.type = "button";
      chip.setAttribute("aria-pressed", String(activeTags.indexOf(tag) !== -1));
      chip.addEventListener("click", function () { toggleTag(tag); });
      tagRow.appendChild(chip);
    });

    var heading = el("h3", null, title);
    body.appendChild(meta);
    if (tagRow.childNodes.length) body.appendChild(tagRow);
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
    var unfiltered = !searchEl.value.trim() && !sourceEl.value && !activeRegion && !activeTags.length;
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
    scopedItems().forEach(function (item) {
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
    scopedItems().forEach(function (item) {
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

  function renderTags(base) {
    var counts = Object.create(null);
    base.forEach(function (item) {
      (item.tags || []).forEach(function (tag) {
        counts[tag] = (counts[tag] || 0) + 1;
      });
    });
    topicsEl.replaceChildren();
    tagOrder.forEach(function (tag) {
      if (!counts[tag]) return;
      var button = el("button", null, tag + " " + counts[tag]);
      button.type = "button";
      button.setAttribute("aria-pressed", String(activeTags.indexOf(tag) !== -1));
      button.addEventListener("click", function () { toggleTag(tag); });
      topicsEl.appendChild(button);
    });
  }

  function renderDates() {
    dateSelect.replaceChildren();
    dateSelect.appendChild(new Option("全部日期", ""));
    indexDates.forEach(function (entry) {
      dateSelect.appendChild(new Option(formatDay(entry.date) + " · " + entry.count + "条", entry.date));
    });
    dateSelect.value = scopeDate;
    var index = dateIndex(scopeDate);
    olderBtn.disabled = !!scopeDate && index >= indexDates.length - 1;
    newerBtn.disabled = !scopeDate;
  }

  function refreshView() {
    headingEl.textContent = scopeDate ? formatDay(scopeDate) : "全部日期";
    renderDates();
    fillSources();
    if (activeRegion && !scopedItems().some(function (item) { return item.region === activeRegion; })) {
      activeRegion = "";
    }
    renderRegions();
    applyFilters();
  }

  function selectScope(date, updateHash) {
    scopeDate = date || "";
    if (updateHash) {
      history.replaceState(null, "", scopeDate ? "#" + scopeDate : "#");
    }
    refreshView();
  }

  function boot(index, catalog) {
    indexDates = (index && index.dates) || [];
    if (catalog && catalog.tags && catalog.tags.length) tagOrder = catalog.tags;
    if (!allItems.length) {
      statusEl.textContent = "还没有数据。每日任务跑过之后，这里会列出各天的条目。";
      headingEl.textContent = "尚无日报";
      return;
    }
    allItems.sort(function (a, b) {
      return String(b.published_at || "").localeCompare(String(a.published_at || ""));
    });
    var hash = (location.hash || "").replace(/^#/, "");
    var known = indexDates.some(function (entry) { return entry.date === hash; });
    selectScope(known ? hash : "", false);
  }

  dateSelect.addEventListener("change", function () {
    selectScope(dateSelect.value, true);
  });
  olderBtn.addEventListener("click", function () {
    if (!scopeDate) {
      if (indexDates.length) selectScope(indexDates[0].date, true);
      return;
    }
    var index = dateIndex(scopeDate);
    if (index >= 0 && index < indexDates.length - 1) selectScope(indexDates[index + 1].date, true);
  });
  newerBtn.addEventListener("click", function () {
    var index = dateIndex(scopeDate);
    if (index > 0) selectScope(indexDates[index - 1].date, true);
    else if (index === 0) selectScope("", true);
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
    if (!hash) {
      if (scopeDate) selectScope("", false);
      return;
    }
    if (hash !== scopeDate && indexDates.some(function (entry) { return entry.date === hash; })) {
      selectScope(hash, false);
    }
  });

  function loadJson(url) {
    return fetch(url, { cache: "no-cache" }).then(function (response) {
      if (!response.ok) throw new Error(url);
      return response.json();
    });
  }

  function loadMonths(months) {
    var pending = months.slice();
    var loaded = [];
    function next() {
      var slice = pending.splice(0, 4);
      if (!slice.length) return Promise.resolve(loaded);
      return Promise.all(slice.map(function (month) {
        return loadJson(month.file).then(function (payload) {
          return (payload && payload.items) || [];
        });
      })).then(function (groups) {
        groups.forEach(function (group) { loaded = loaded.concat(group); });
        return next();
      });
    }
    return next();
  }

  statusEl.textContent = "正在加载选题库…";
  Promise.all([loadJson("data/index.json"), loadJson("data/search-index.json")])
    .then(function (pair) {
      var index = pair[0];
      var catalog = pair[1];
      var months = (catalog && catalog.months) || [];
      var first = months.slice(0, 2);
      var rest = months.slice(2);
      return loadMonths(first).then(function (items) {
        allItems = items;
        boot(index, catalog);
        if (!rest.length) return;
        statusEl.textContent = statusEl.textContent + " 正在补齐更早的月份…";
        return loadMonths(rest).then(function (older) {
          allItems = allItems.concat(older);
          refreshView();
        });
      });
    })
    .catch(function () {
      statusEl.textContent = "读不到搜索索引。请确认 data/search-index.json 已生成。";
    });
})();

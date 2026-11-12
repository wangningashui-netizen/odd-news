(function () {
  "use strict";

  var PAGE = 18;
  var WEEK = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"];
  var REGION_ORDER = ["", "全球", "印度", "英国", "美国", "日本", "爱尔兰"];

  var dateSelect = document.getElementById("date-select");
  var olderBtn = document.getElementById("older-day");
  var newerBtn = document.getElementById("newer-day");
  var regionsEl = document.getElementById("regions");
  var sortEl = document.getElementById("sort");
  var angleEl = document.getElementById("angle");
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
  var activeAngle = "";
  var activeTags = [];
  var sortMode = "time";
  var detailId = "";
  var PAGES_ORIGIN = "https://wangningashui-netizen.github.io/odd-news/";
  var initialSource = "";
  try {
    initialSource = new URLSearchParams(window.location.search).get("source") || "";
  } catch (err) {
    initialSource = "";
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function mediaUrl(url) {
    if (!url) return "";
    if (url.indexOf(PAGES_ORIGIN) === 0 && window.location.host !== "wangningashui-netizen.github.io") {
      return url.slice(PAGES_ORIGIN.length);
    }
    return url;
  }

  function safeHttp(url) {
    if (!url) return "";
    try {
      var parsed = new URL(mediaUrl(url), window.location.href);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.href;
    } catch (err) {
      return "";
    }
    return "";
  }

  function hashValue() {
    return (window.location.hash || "").replace(/^#/, "");
  }

  function hashDetail() {
    var hash = hashValue();
    if (hash.indexOf("x=") === 0) return decodeURIComponent(hash.slice(2));
    return "";
  }

  function hashDate() {
    var hash = hashValue();
    if (!hash || hash.indexOf("x=") === 0) return "";
    return hash;
  }

  function heatScore(item) {
    if (item.reddit_score != null && item.reddit_score !== "") return Number(item.reddit_score) || 0;
    var metrics = item.x && item.x.public_metrics;
    if (metrics && metrics.like_count != null) return Number(metrics.like_count) || 0;
    return 0;
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
    var extra = item.x || {};
    var author = extra.author || {};
    return [item.title_zh, item.title_en, item.summary_zh, item.summary_en, extra.text, author.name, author.username]
      .filter(Boolean)
      .join("\n")
      .toLowerCase();
  }

  function scopedItems() {
    if (!scopeDate) return allItems;
    return allItems.filter(function (item) { return item.date === scopeDate; });
  }

  function baseFiltered() {
    if (detailId) {
      return allItems.filter(function (item) { return item.id === detailId; });
    }
    var query = searchEl.value.trim().toLowerCase();
    var source = sourceEl.value;
    return scopedItems().filter(function (item) {
      if (source && item.source !== source) return false;
      if (activeRegion && item.region !== activeRegion) return false;
      if (activeAngle) {
        var angle = item.x && item.x.angle;
        if (item.kind !== "x" || angle !== activeAngle) return false;
      }
      if (query && haystack(item).indexOf(query) === -1) return false;
      return true;
    });
  }

  function clusterGroups(matched) {
    var matchedIds = Object.create(null);
    matched.forEach(function (item) { matchedIds[item.id] = true; });
    var byId = Object.create(null);
    allItems.forEach(function (item) {
      var key = item.cluster_id || item.id;
      if (!byId[key]) byId[key] = [];
      byId[key].push(item);
    });
    var seen = Object.create(null);
    var groups = [];
    matched.forEach(function (item) {
      var key = item.cluster_id || item.id;
      if (seen[key]) return;
      seen[key] = true;
      var members = (byId[key] || [item]).slice().sort(function (a, b) {
        return String(b.published_at || "").localeCompare(String(a.published_at || ""));
      });
      var rep = null;
      members.forEach(function (member) {
        if (!matchedIds[member.id]) return;
        if (!rep) rep = member;
        else if (member.image && !rep.image) rep = member;
      });
      groups.push({ key: key, rep: rep || members[0], members: members });
    });
    groups.sort(function (a, b) {
      if (sortMode === "heat") {
        var size = (b.rep.cluster_item_count || b.members.length || 1) - (a.rep.cluster_item_count || a.members.length || 1);
        if (size) return size;
        var score = heatScore(b.rep) - heatScore(a.rep);
        if (score) return score;
      }
      return String(b.rep.published_at || "").localeCompare(String(a.rep.published_at || ""));
    });
    return groups;
  }

  function applyFilters() {
    var base = baseFiltered();
    var matched = base.filter(function (item) {
      if (!activeTags.length) return true;
      var tags = item.tags || [];
      return activeTags.some(function (tag) { return tags.indexOf(tag) !== -1; });
    });
    filtered = clusterGroups(matched);
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
    statusEl.textContent = where + "，当前显示 " + visible + " / " + matched + " 组。";
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

  function copyText(text, button) {
    function done() {
      button.textContent = "已复制";
      window.setTimeout(function () { button.textContent = "复制"; }, 1600);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(); });
      return;
    }
    fallback();
    function fallback() {
      var area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      try { document.execCommand("copy"); done(); } catch (err) { button.textContent = "请手动复制"; }
      area.remove();
    }
  }

  function zoomImage(src, caption) {
    return function () { openLightbox(src, caption); };
  }

  function appendXMaterial(body, item) {
    var extra = item.x || {};
    var block = el("div", "x-block");
    if (item.summary_zh && item.summary_zh !== (item.title_zh || "")) {
      var summary = el("p", "summary");
      summary.appendChild(el("span", "summary-label", "概要"));
      summary.appendChild(document.createTextNode(item.summary_zh));
      block.appendChild(summary);
    } else if (item.summary_zh && !item.title_zh) {
      var only = el("p", "summary");
      only.appendChild(el("span", "summary-label", "概要"));
      only.appendChild(document.createTextNode(item.summary_zh));
      block.appendChild(only);
    }
    var original = extra.text || item.summary_en || "";
    if (original) {
      var textWrap = el("div", "x-text");
      textWrap.lang = extra.lang || "und";
      textWrap.appendChild(el("span", "summary-label", "原文"));
      textWrap.appendChild(document.createTextNode(original));
      block.appendChild(textWrap);
    }
    var photos = extra.photos || [];
    if (photos.length) {
      var gallery = el("div", "x-photos");
      photos.forEach(function (photo, index) {
        var src = safeHttp(photo);
        if (!src) return;
        var button = el("button", "x-photo");
        button.type = "button";
        var image = document.createElement("img");
        image.src = src;
        image.alt = "配图 " + (index + 1);
        image.referrerPolicy = "no-referrer";
        image.loading = "lazy";
        button.appendChild(image);
        button.addEventListener("click", zoomImage(src, item.title_zh || "配图"));
        gallery.appendChild(button);
      });
      if (gallery.childNodes.length) block.appendChild(gallery);
    }
    var actions = el("div", "x-actions");
    var postUrl = safeHttp(extra.post_url || item.url);
    if (postUrl) {
      var postLink = el("a", "read", "原帖");
      postLink.href = postUrl;
      postLink.target = "_blank";
      postLink.rel = "noopener noreferrer";
      actions.appendChild(postLink);
    }
    if (extra.has_video) {
      var videoUrl = safeHttp(extra.video_url);
      if (videoUrl) {
        var videoLink = el("a", "read warn-link", "视频直链（可能过期）");
        videoLink.href = videoUrl;
        videoLink.target = "_blank";
        videoLink.rel = "noopener noreferrer";
        actions.appendChild(videoLink);
      } else {
        actions.appendChild(el("span", "x-label", "这次没有解析到视频直链"));
      }
    }
    if (!detailId) {
      var alone = el("a", "read", "单独查看");
      alone.href = "#x=" + encodeURIComponent(item.id);
      actions.appendChild(alone);
    }
    block.appendChild(actions);
    var command = extra.ytdlp_command || (postUrl ? "yt-dlp " + (extra.post_url || item.url) : "");
    if (command) {
      var row = el("div", "x-cmd");
      var code = el("code", null, command);
      var copy = el("button", "copy", "复制");
      copy.type = "button";
      copy.addEventListener("click", function () { copyText(command, copy); });
      row.appendChild(code);
      row.appendChild(copy);
      block.appendChild(row);
      block.appendChild(el("p", "x-note", "视频直链会过期。失效时用上面的命令重新解析，不要把视频文件放进仓库。"));
    }
    if (extra.comments_image) {
      var sheetSrc = safeHttp(extra.comments_image);
      if (sheetSrc) {
        block.appendChild(el("p", "x-label", "评论区长图（根据真实回复渲染，不是截图）"));
        if (extra.replies_omitted) {
          block.appendChild(el("p", "x-note", "已去掉贬损国籍、民族、宗教、种姓，或套用族群刻板印象的回复。"));
        }
        var sheetBtn = el("button", "x-sheet");
        sheetBtn.type = "button";
        var sheet = document.createElement("img");
        sheet.src = sheetSrc;
        sheet.alt = "评论区长图";
        sheet.referrerPolicy = "no-referrer";
        sheet.loading = "lazy";
        sheet.className = "x-comments";
        sheetBtn.appendChild(sheet);
        sheetBtn.addEventListener("click", zoomImage(sheetSrc, "评论区长图"));
        block.appendChild(sheetBtn);
      }
    }
    body.appendChild(block);
  }

  function makeCard(group, hero) {
    var item = group.rep || group;
    var members = group.members || [item];
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
    if (item.kind === "x") card.classList.add("x-card");
    if (item.x && item.x.has_video) thumb.classList.add("has-video");
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
    if (item.kind === "x" && item.x && item.x.angle) {
      var angleClass = item.x.angle === "官方" ? "badge angle-official" : "badge angle-oddity";
      meta.appendChild(el("span", angleClass, item.x.angle === "官方" ? "官方" : "离谱合集"));
    }
    if (item.kind === "x" && item.x && item.x.public_metrics) {
      var xm = item.x.public_metrics;
      var bits = [];
      if (xm.like_count != null) bits.push("赞 " + xm.like_count);
      if (xm.repost_count != null) bits.push("转 " + xm.repost_count);
      if (xm.reply_count != null) bits.push("评 " + xm.reply_count);
      if (xm.impression_count != null) bits.push("看 " + xm.impression_count);
      if (bits.length) meta.appendChild(el("span", "heat-line", bits.join(" · ")));
    } else if (item.reddit_score != null || item.reddit_comments != null) {
      meta.appendChild(el("span", "heat-line", "▲ " + (item.reddit_score || 0) + " · 💬 " + (item.reddit_comments || 0)));
    }

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
    if (item.kind !== "x" && item.title_zh && item.title_en) {
      var en = el("p", "title-en", item.title_en);
      en.lang = "en";
      body.appendChild(en);
    }
    var summaryText = item.summary_zh || item.summary_en || "";
    if (item.kind !== "x" && summaryText && summaryText !== title) {
      var summary = el("p", "summary");
      var label = el("span", "summary-label", "概要");
      summary.appendChild(label);
      summary.appendChild(document.createTextNode(summaryText));
      body.appendChild(summary);
    }
    if (item.kind === "x" && item.x) appendXMaterial(body, item);
    else {
      var link = safeHttp(item.url);
      if (link) {
        var anchor = el("a", "read", "阅读原文");
        anchor.href = link;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        body.appendChild(anchor);
      }
    }
    var clusterCount = item.cluster_item_count || members.length;
    var clusterSources = item.cluster_source_count || 1;
    if (clusterCount > 1) {
      var toggle = el("button", "cluster-toggle", clusterSources + "家来源 · " + clusterCount + "条");
      toggle.type = "button";
      toggle.setAttribute("aria-expanded", "false");
      var list = el("ul", "cluster-list");
      list.hidden = true;
      members.forEach(function (member) {
        var li = document.createElement("li");
        var memberLink = safeHttp(member.url);
        var label = member.title_zh || member.title_en || "无标题";
        if (memberLink) {
          var memberAnchor = el("a", null, label);
          memberAnchor.href = memberLink;
          memberAnchor.target = "_blank";
          memberAnchor.rel = "noopener noreferrer";
          li.appendChild(memberAnchor);
        } else {
          li.appendChild(document.createTextNode(label));
        }
        li.appendChild(document.createTextNode(" · " + (member.source || "")));
        list.appendChild(li);
      });
      toggle.addEventListener("click", function () {
        list.hidden = !list.hidden;
        toggle.setAttribute("aria-expanded", String(!list.hidden));
      });
      body.appendChild(toggle);
      body.appendChild(list);
    }
    card.appendChild(thumb);
    card.appendChild(body);
    return card;
  }

  function appendMore() {
    var unfiltered = !searchEl.value.trim() && !sourceEl.value && !activeRegion && !activeTags.length && !activeAngle;
    var next = filtered.slice(shown, shown + PAGE);
    next.forEach(function (group, index) {
      var heroItem = next[index].rep || next[index];
      var hero = unfiltered && shown === 0 && index === 0 && heroItem.kind !== "x";
      gridEl.appendChild(makeCard(group, hero));
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
    if (initialSource && seen[initialSource]) {
      sourceEl.value = initialSource;
      initialSource = "";
    } else if (seen[previous]) sourceEl.value = previous;
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

  function updateDetailBar() {
    var bar = document.getElementById("detail-bar");
    if (!bar) return;
    document.body.classList.toggle("detail", !!detailId);
    if (!detailId) {
      bar.hidden = true;
      bar.replaceChildren();
      return;
    }
    bar.hidden = false;
    bar.replaceChildren();
    var back = el("a", "detail-back", "返回全部");
    back.href = "#";
    back.addEventListener("click", function (event) {
      event.preventDefault();
      if (window.history && window.history.pushState) window.history.pushState(null, "", window.location.pathname + window.location.search);
      else window.location.hash = "";
      detailId = "";
      refreshView();
    });
    bar.appendChild(back);
    var item = null;
    allItems.forEach(function (candidate) {
      if (candidate.id === detailId) item = candidate;
    });
    if (item) bar.appendChild(document.createTextNode(" · " + (item.title_zh || item.title_en || "这条素材")));
    else bar.appendChild(document.createTextNode(" · 没有这条素材"));
  }

  function refreshView() {
    updateDetailBar();
    headingEl.textContent = detailId ? "这条素材" : (scopeDate ? formatDay(scopeDate) : "全部日期");
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
    detailId = hashDetail();
    var hash = hashDate();
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
  sortEl.addEventListener("change", function () {
    sortMode = sortEl.value || "time";
    applyFilters();
  });
  if (angleEl) {
    angleEl.addEventListener("change", function () {
      activeAngle = angleEl.value || "";
      applyFilters();
    });
  }
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
    detailId = hashDetail();
    if (detailId) {
      refreshView();
      return;
    }
    var hash = hashDate();
    if (!hash) {
      if (scopeDate) selectScope("", false);
      else refreshView();
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

  setupMobileChrome();

  statusEl.textContent = "正在加载选题库…";

  function setupMobileChrome() {
    var toolbar = document.getElementById("toolbar");
    var spacer = document.getElementById("toolbar-spacer");
    var bar = document.getElementById("mobile-bar");
    var toggle = document.getElementById("filter-toggle");
    var label = toggle ? toggle.querySelector(".filter-toggle-label") : null;
    var backdrop = document.getElementById("filter-backdrop");
    if (!toolbar || !spacer || !bar || !toggle || !label || !backdrop) return;

    var mq = window.matchMedia("(max-width: 719px), (max-height: 520px)");
    var overlay = false;
    var scrollAtOpen = 0;
    var lockUntil = 0;
    var wasMobile = false;
    var barShown = false;
    var ticking = false;
    var relockTimer = 0;

    function mobile() { return !!mq.matches; }

    function setLabel(open) {
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      label.textContent = open ? "收起" : "筛选";
    }

    function filtersActive() {
      var search = document.getElementById("search");
      var source = document.getElementById("source");
      var sort = document.getElementById("sort");
      var angle = document.getElementById("angle");
      var regionOn = false;
      var regionButtons = document.querySelectorAll("#regions button[aria-pressed='true']");
      var i;
      for (i = 0; i < regionButtons.length; i += 1) {
        if ((regionButtons[i].textContent || "").indexOf("全部地区") !== 0) regionOn = true;
      }
      var tagOn = !!document.querySelector("#topics button[aria-pressed='true']");
      return !!((search && search.value.trim()) ||
        (source && source.value) ||
        (sort && sort.value && sort.value !== "time") ||
        (angle && angle.value) ||
        regionOn || tagOn);
    }

    function markActive() {
      toggle.classList.toggle("has-active", filtersActive());
    }

    function showBar(show) {
      barShown = !!show && mobile();
      bar.hidden = !barShown;
    }

    function syncPin() {
      var vv = window.visualViewport;
      var top = vv ? (vv.offsetTop || 0) : 0;
      var shift = top ? "translate3d(0," + top + "px,0)" : "";
      bar.style.transform = shift;
      toolbar.style.transform = overlay ? shift : "";
    }

    function closeOverlay() {
      if (!overlay) return;
      overlay = false;
      toolbar.classList.remove("is-overlay");
      spacer.hidden = true;
      spacer.style.height = "0px";
      backdrop.hidden = true;
      setLabel(false);
      syncPin();
      lockUntil = Date.now() + 350;
    }

    function openOverlay() {
      if (overlay || !mobile()) return;
      showBar(true);
      var barHeight = bar.getBoundingClientRect().height || 48;
      document.documentElement.style.setProperty("--mobile-bar-offset", barHeight + "px");
      var height = toolbar.getBoundingClientRect().height;
      if (height < 1) return;
      spacer.style.height = height + "px";
      spacer.hidden = false;
      toolbar.classList.add("is-overlay");
      toolbar.scrollTop = 0;
      overlay = true;
      backdrop.hidden = false;
      setLabel(true);
      scrollAtOpen = window.scrollY || window.pageYOffset || 0;
      syncPin();
      lockUntil = Date.now() + 350;
    }

    function resetDesktop() {
      closeOverlay();
      showBar(false);
      toolbar.classList.remove("is-overlay");
      spacer.hidden = true;
      spacer.style.height = "0px";
      toolbar.style.transform = "";
      setLabel(false);
    }

    function naturalBottom() {
      return (overlay ? spacer : toolbar).getBoundingClientRect().bottom;
    }

    function update() {
      if (!mobile()) {
        if (wasMobile || overlay || barShown) resetDesktop();
        wasMobile = false;
        return;
      }
      wasMobile = true;
      syncPin();
      markActive();
      var y = window.scrollY || window.pageYOffset || 0;
      if (overlay && Date.now() < lockUntil) {
        if (!relockTimer) {
          relockTimer = window.setTimeout(function () {
            relockTimer = 0;
            update();
          }, Math.max(16, lockUntil - Date.now() + 16));
        }
      } else if (overlay) {
        var spacerBottom = spacer.getBoundingClientRect().bottom;
        var dy = y - scrollAtOpen;
        if (spacerBottom > 48 || dy > 48 || dy < -48) closeOverlay();
      }
      var bottom = naturalBottom();
      if (overlay) showBar(true);
      else if (bottom < -4) showBar(true);
      else if (bottom > 20) showBar(false);
    }

    function requestUpdate() {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(function () {
        ticking = false;
        update();
      });
    }

    toggle.addEventListener("click", function () {
      if (!mobile()) return;
      if (overlay) closeOverlay();
      else openOverlay();
      update();
    });
    backdrop.addEventListener("click", function () {
      closeOverlay();
      update();
    });
    backdrop.addEventListener("touchmove", function () {
      if (!overlay) return;
      closeOverlay();
      update();
    }, { passive: true });
    backdrop.addEventListener("wheel", function () {
      if (!overlay) return;
      closeOverlay();
      update();
    }, { passive: true });
    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape" || !overlay) return;
      var box = document.getElementById("lightbox");
      if (box && !box.hidden) return;
      closeOverlay();
      update();
    });
    toolbar.addEventListener("input", markActive);
    toolbar.addEventListener("change", markActive);
    toolbar.addEventListener("click", function () { window.setTimeout(markActive, 0); });
    window.addEventListener("scroll", requestUpdate, { passive: true });
    window.addEventListener("resize", requestUpdate);
    window.addEventListener("pageshow", requestUpdate);
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", requestUpdate);
      window.visualViewport.addEventListener("scroll", requestUpdate);
    }
    if (mq.addEventListener) mq.addEventListener("change", requestUpdate);
    else if (mq.addListener) mq.addListener(requestUpdate);
    update();
  }
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

# 奇闻日报

给中文读者找故事选题用的静态奇闻聚合。页面只做收集和去重，不排名、不筛选“最怪的那几条”。每个来源当天发出的条目都会留下。

界面上的名字用的是 **奇闻日报**。如果想换一个更短的刊名，**异闻录** 比较合适：三个字，能看出来是在记奇怪的事，也不像日报那样绑死“一天一刊”。

## 页面上有什么

每条都有：

- 中文标题，英文原标题用小一号字留在下面
- 概要（两到四句；翻译失败时先显示英文原文，并标成「待翻译」）
- 主图（只存图片地址，热链接，不把图片文件放进仓库）
- 来源、地区（按来源判断，例如印度、英国、美国、日本、全球）
- 北京时间
- 「阅读原文」（新标签页打开）

图片用 `referrerpolicy="no-referrer"` 和懒加载。加载失败或来源没有主图时，换成站内的占位图。点图片可以看大图。

默认打开最新一天。日期可以用下拉框和「上一天 / 下一天」切换。可以按来源、地区筛选，也可以同时搜索中英文标题和概要。条目多的时候往下滚会继续加载。颜色跟随系统的浅色 / 深色。

页脚写明：文章和图片版权属于原发布者，本站只做链接。

## 仓库里有什么

| 路径 | 作用 |
| --- | --- |
| `index.html` `styles.css` `app.js` | 页面，没有构建步骤，也没有外部依赖 |
| `assets/` | 占位图和图标 |
| `.nojekyll` | 让 GitHub Pages 不要用 Jekyll 处理这个仓库 |
| `data/YYYY-MM-DD.json` | 某一天的条目，日期按发布时间的北京时间计算 |
| `data/index.json` | 日期列表，新的在前，带每天的条数 |
| `scripts/fetch_news.py` | 抓取、去重、翻译、写 JSON。只用 Python 标准库 |
| `.github/workflows/daily-fetch.yml` | 每天自动跑上面的脚本并提交 |

条目按规范化后的原文链接去重（忽略 `utm_*` 之类的跟踪参数，`www` 和协议差异也算同一条）。同一条故事如果先出现在通讯社、后出现在 Reddit，会留下先抓到的那条。

`translation_status` 有三种：

- `ok`：GitHub Models 生成的中文标题和概要
- `fallback`：模型不可用时的机器翻译，页面上标「机翻」。下次如果模型能用，会把最近 7 天里的机翻换成模型概要
- `pending`：中文还没写上。页面显示英文，并标「待翻译」。下次运行会重试最近 7 天里的这些条目

## 自动更新

工作流同时支持定时和手动：

- 定时：`0 23 * * *`（GitHub 的 cron 用 UTC）。23:00 UTC 是北京时间第二天早上 7:00。中国不实行夏令时，所以全年都是这个点。
- 手动：Actions 页面里的 **Run workflow**。

工作流权限是 `contents: write` 和 `models: read`。抓取脚本用 `GITHUB_TOKEN` 调用 `https://models.github.ai/inference/chat/completions`，默认模型是 `openai/gpt-4o-mini`（小、便宜）。一次请求里放多条，减少免费额度的请求次数。

模型如果返回限流，会退避重试。如果接口不可用、没有返回补全，或者根本没有 token，条目仍然会写入。脚本接着用公开的机器翻译接口补中文，并标成 `fallback`。机器翻译也失败时，保留英文，标成 `pending`。

提交发生在 `main`（或你手动运行时所在的分支）上。GitHub Pages 如果选的是「从分支部署 / main / 根目录」，这次提交会触发重新部署，不需要单独的构建。

### 你需要在 GitHub 上点的设置

仓库合并到 `main` 之后，定时任务才会按默认分支上的工作流运行。请逐项确认：

1. **Pages**：Settings → Pages → Build and deployment → Source 选 **Deploy from a branch**，Branch 选 **main**，文件夹选 **/ (root)**，保存。  
   项目站地址会是 `https://<用户名>.github.io/odd-news/`。页面里的数据路径是相对的，不依赖域名根路径。
2. **Actions 可以写仓库**：Settings → Actions → General → Workflow permissions 选 **Read and write permissions**。工作流文件里已经写了 `contents: write`；如果仓库把工作流锁成只读，推送数据会 403。
3. **Actions 已启用**。新仓库有时要先打开 Actions 标签页，允许工作流运行。
4. 合并这个拉取请求。定时任务只认默认分支上的工作流文件。

不需要配密钥。`GITHUB_TOKEN` 由 Actions 自动注入。

GitHub Models 已于 2026-07-30 停用：`models.github.ai` 现在对补全请求只返回纯文本 `OK`，不是 JSON。工作流仍会按上面的方式去调用它，这样服务如果恢复，或者你把下面的变量指到一个兼容 OpenAI 的接口，不用改代码：

| 变量 | 作用 |
| --- | --- |
| `MODELS_API_URL` | 默认 `https://models.github.ai/inference/chat/completions` |
| `MODELS_API_KEY` | 默认用 `GITHUB_TOKEN` |
| `MODELS_MODEL` | 默认 `openai/gpt-4o-mini` |

在仓库 Secrets 里加上 `MODELS_API_KEY` 时，要在工作流的 `env` 里把它传给脚本（现在只传了 `GITHUB_TOKEN`）。不配的话，每天的结果会是「机翻」，页面照常更新。

不想要机器翻译时，用 `python scripts/fetch_news.py --no-fallback`。本地调试也可以加 `--no-enrich`（跳过补主图和摘要）或 `--no-models`。

## 来源

2026-11-08 在这台环境里逐个请求过。下面的「窗口条数」是当时一条 feed 里返回的条目数，不是去重后的每日新增。

### 在用

| 来源 | 地区 | 地址 | 窗口条数 |
| --- | --- | --- | --- |
| Oddity Central | 全球 | `https://www.odditycentral.com/feed` | 10 |
| All That's Interesting | 全球 | `https://allthatsinteresting.com/feed` | 100 |
| Oddee | 全球 | `https://www.oddee.com/feed/` | 10 |
| UPI Odd News | 美国 | `https://rss.upi.com/news/odd_news.rss` | 25 |
| Atlas Obscura | 全球 | `https://www.atlasobscura.com/feeds/latest` | 27 |
| Mirror Weird News | 英国 | `https://www.mirror.co.uk/news/weird-news/?service=rss` | 25 |
| Daily Star Weird News | 英国 | `https://www.dailystar.co.uk/news/weird-news/?service=rss` | 24 |
| Irish Mirror Weird News | 爱尔兰 | `https://www.irishmirror.ie/news/weird-news/?service=rss` | 2 |
| Metro Weird | 英国 | `https://metro.co.uk/news/weird/feed/` | 23 |
| Express Weird News | 英国 | `https://www.express.co.uk/news/weird?service=rss` | 10 |
| New York Post Weird But True | 美国 | `https://nypost.com/weird-but-true/feed/` | 20 |
| Hindustan Times Trending | 印度 | `https://www.hindustantimes.com/feeds/rss/trending/rssfeed.xml` | 32 |
| India Today Trending | 印度 | `https://www.indiatoday.in/rss/1797650` | 20 |
| Times of India Viral News | 印度 | `https://timesofindia.indiatimes.com/rssfeeds/59016670.cms` | 20 |
| SoraNews24 | 日本 | `https://soranews24.com/feed/` | 20 |
| Neatorama | 全球 | `https://www.neatorama.com/feed/` | 15 |
| LADbible Weird | 英国 | `https://www.ladbible.com/weird.rss` | 25 |
| UNILAD Weird | 英国 | `https://www.unilad.com/weird.rss` | 25 |
| NDTV Offbeat | 印度 | 见下方说明 | 27 |
| Reddit r/nottheonion | 全球 | `https://www.reddit.com/r/nottheonion/new/.rss?limit=100` | 100 |
| Reddit r/Offbeat | 全球 | `https://www.reddit.com/r/Offbeat/new/.rss?limit=100` | 100 |

Reddit 使用固定的 User-Agent：`linux:odd-news-daily:1.0.0 (by /u/odd-news-daily)`。外链帖打开原文，站内自帖丢掉。不要把这个标识改成编程语言的默认值，否则会被拒绝。

NDTV：`https://feeds.feedburner.com/ndtvnews-offbeat` 返回的是首页 HTML，不是 RSS；`ndtv.com` 的栏目页从很多数据中心 IP 返回 403。现在用 Google News 的栏目查询 `site:ndtv.com/offbeat when:3d`，再把 `news.google.com` 的跳转解回 `www.ndtv.com` 的文章地址。解不开的条目不会入库。

Reach 旗下的地方版（WalesOnline、Manchester Evening News 等）大量转发 Mirror 的同一篇稿，链接不同、去重去不掉，所以没有全部加进来。

### 试过但不能用

| 来源 | 试过的地址 | 结果 |
| --- | --- | --- |
| HuffPost Weird News | `https://www.huffpost.com/section/weird-news/feed` | 能打开，频道是空的（0 条）。栏目页还在，feed 不再出稿 |
| AP News Oddities | `https://apnews.com/oddities`、`https://apnews.com/hub/oddities` | 403，没有可用的 RSS。用 Google News 搜 “oddities” 得到的是旧闻，不是这个栏目的当日列表 |
| The Sun weird | `/news/weird/feed/`、`/news/weird-news/feed/`、`/topic/weird/feed/` | RSS 合法但 0 条。网页是设备验证墙。全站 feed 是普通新闻，不是怪闻栏，所以没有拿全站来凑数。英国怪闻改由 Mirror、Daily Star、Metro、Express、LADbible、UNILAD 补上 |
| DailyO What The | `/feed`、`/rss.xml`、`/news/what-the/feed` | 都是 404。栏目页还在，最新文章停在 2023-12 |
| Reddit r/weirdnews | `/r/weirdnews/new/.rss` 和 `hot` | 返回的是 2019–2020 的旧帖，不是在更新的 feed |

## 第一次抓取（2026-11-08）

在这台环境里跑了 `python scripts/fetch_news.py`。

- 21 个在用来源全部成功，0 个失败
- 去重后 **651** 条，其中 **587** 条有主图地址
- 最近几天（按文章发布时间的北京时间）：11 月 8 日 48 条（当天晚上的快照，还没过完）、11 月 7 日 76 条、11 月 6 日 86 条、11 月 5 日 56 条。feed 窗口里更早的稿件也按原日期归档了
- **GitHub Models 没有译成。** 本机没有 `GITHUB_TOKEN`。另外直接请求 `https://models.github.ai/inference/chat/completions` 得到 HTTP 200 和纯文本 `OK`，不是聊天补全。651 条都用机器翻译写成了中文，`translation_status` 为 `fallback`。工作流每天仍会先试 Models；模型恢复后，最近 7 天的「机翻」会被换成模型概要

每天真正的新增取决于来源当天发了多少。上面这几天大约是 50–90 条。Reddit、印度趋势和英国怪闻栏忙的时候会更高。脚本不会为了凑数去抓普通新闻版。

## 本地查看

```bash
python3 scripts/fetch_news.py
python3 -m http.server 8765
```

浏览器打开 `http://127.0.0.1:8765/`。不要用 `file://` 打开，否则读不到 `data/`。

中文用系统字体（苹方、思源黑体、微软雅黑等），没有从 CDN 拉字体。

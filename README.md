# 奇闻日报

给创作工具直接读的印度素材库。页面只收集和打包，不替 Claude / Codex 做二次加工。中文界面、选题标签、跨日搜索、按热度排序、`data/translations/` 这条翻译流都还在。

只留内容地区是 **印度** 的条目。判断用的是正文里的地区（`scripts/content_region.py`），不是发布方。印度媒体转载的外国新闻不会入库。X 这条通道收的是外面任务已经圈定的印度帖，地区固定为印度。

界面上的名字仍是 **奇闻日报**。

## 页面上有什么

新闻条目：

- 中文标题，英文原标题用小一号字留在下面
- 概要（两到四句；翻译失败时先显示英文原文，并标成「待翻译」）
- 主图（新闻仍是热链接，不把新闻图片放进仓库）
- 来源、地区
- 北京时间
- 「阅读原文」

X 条目另外有：中文标题和概要、原文全文、图片、评论区长图、视频直链（标明会过期）、原帖链接，以及可以直接复制的 `yt-dlp <原帖 URL>`。点「单独查看」只看这一条。

图片用 `referrerpolicy="no-referrer"` 和懒加载。加载失败或来源没有主图时，换成站内的占位图。点图片可以看大图。

打开时默认是「全部日期」：搜索、来源、地区、选题标签都作用在所有日期上，结果按发布时间从新到旧排，往下滚继续加载。日期下拉里选某一天，就只看那一天；「下一天」在最新一天上会回到全部日期。

每条有 1 到 3 个选题标签（给短视频找素材用）。标签条可以多选，数字是当前搜索和来源、地区条件下的条数。点卡片上的标签也会加入筛选。颜色跟随系统的浅色 / 深色。

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
| `.github/workflows/daily-fetch.yml` | 每天自动跑上面的脚本，并刷新最近 7 天的 X 视频直链 |
| `data/x/inbox/YYYY-MM-DD.json` | 外面的任务提交的 X 原始帖。格式见 `docs/x-schema.md` |
| `scripts/ingest_x.py` | 下载图片和头像、解析视频直链、渲染评论长图、写入站点数据和 AI 月文件 |
| `.github/workflows/ingest-x.yml` | `data/x/inbox/**` 有推送时跑上面的脚本，也可手动跑 |
| `assets/x/<推文 id>/` | 图片、头像、视频封面、评论长图。没有视频文件 |

条目按规范化后的原文链接去重（忽略 `utm_*` 之类的跟踪参数，`www` 和协议差异也算同一条）。同一条故事如果先出现在通讯社、后出现在 Reddit，会留下先抓到的那条。

选题标签由 `scripts/topics.py` 里的英文关键词规则打上，规则写在文件里，可以直接改。一条命中就打上对应标签，最多三个；都没命中就是「其他」。每天的抓取会对没有模型标签的条目重算。如果设置了 `MODELS_API_URL` 或 `MODELS_API_KEY`，抓取会再试一次模型打标，成功的条目标成 `tag_source: model`，以后不再被规则覆盖。

没有主图或没有真正摘要的条目（尤其是从 Google News 解出来的 NDTV、News18、Times Now、Republic）会再打开原文页，读取 `og:image` / `twitter:image` 和 `og:description`（没有就用第一段正文），然后把这段英文机译成概要。抓取失败会换一个浏览器标识再试一次，最多两次，避免每天空打同一页。

跨日搜索不逐个下载每天的大文件。抓取脚本会写 `data/search-index.json` 和按月拆开的 `data/search/YYYY-MM.json`。页面先读最近两个月，先画出结果，再在后台补更早的月份。

`translation_status`：

- `ai`：写进 `data/translations/` 后套用的中文。页面不显示「机翻」
- `ok`：原文本身已是中文，或可选的 `MODELS_API_*` 接口译成的。页面不显示「机翻」
- `fallback`：机器翻译，页面标「机翻」
- `pending`：还没有中文，页面标「待翻译」

每条的稳定键是 `id`（规范化链接的 sha1 前 16 位）。每天 07:00（北京时间）抓取之后，最新一天里还需要翻译的条目（`fallback` 和 `pending`）写在：

`https://wangningashui-netizen.github.io/odd-news/data/untranslated/latest.json`

字段是 `id`、`title_en`、`summary_en`、当前的 `title_zh` / `summary_zh`，另外有 `url` 和 `source`。把译好的结果提交到 `data/translations/YYYY-MM-DD.json`：

```json
{
  "0123abcd4567ef89": {
    "title_zh": "中文标题",
    "summary_zh": "两到四句概要，不加油添醋。"
  }
}
```

文件名里的日期只是这次翻译的批次。套用时按 `id` 找条目，不要求条目落在同一天。推到 `main` 的 `data/translations/**` 会触发 Apply translations 工作流；每天的抓取结束时也会再套用一次，避免重新抓取把已套用的中文盖掉。本地：

```bash
python3 scripts/retranslate.py
python3 scripts/export_untranslated.py
```

## X 素材

外面的任务把原始 JSON 提交到 `data/x/inbox/YYYY-MM-DD.json`。字段、回复结构和一条真样例写在 [`docs/x-schema.md`](docs/x-schema.md)。要抓哪些关键词和账号写在 [`data/x/targets.json`](data/x/targets.json)，本仓库的 Actions 不抓 X，也不保存 X 的 API 密钥。收件箱可以不写 `angle`；不写就按那个文件推断成「官方」或「离谱」。

评论长图是按真实回复渲染的，不是截图。渲染前会去掉贬损国籍、民族、宗教、种姓或套用族群刻板印象的回复，规则在 `scripts/reply_filter.py`。

推送这个路径会跑 `.github/workflows/ingest-x.yml`（也可以手动跑）。它对每条帖子：

1. 用浏览器 User-Agent 把图片、视频封面、头像下载到 `assets/x/<推文 id>/`（`pbs.twimg.com` 对默认 UA 返回 403）
2. `yt-dlp -g -f "b[ext=mp4]/best[ext=mp4]/best"` 解析直链，不下载视频，不用 cookie
3. 用无头 Chrome 按 2 倍缩放渲染白底评论长图，裁掉底部空白，存成 `comments.png`
4. 写入当天数据和 `data/search/YYYY-MM.json`。图片用 `https://wangningashui-netizen.github.io/odd-news/...` 绝对地址

直链会过期。每天 07:00（北京时间）的抓取会再解析最近 7 天 X 条目的直链。页面上同时留着原帖和 `yt-dlp <原帖 URL>`。

## 自动更新

工作流同时支持定时和手动：

- 定时：`0 23 * * *`（GitHub 的 cron 用 UTC）。23:00 UTC 是北京时间第二天早上 7:00。中国不实行夏令时，所以全年都是这个点。
- 手动：Actions 页面里的 **Run workflow**。

抓取里的中文默认仍是机器翻译（`fallback`）。可选的 `MODELS_API_URL` / `MODELS_API_KEY` / `MODELS_MODEL` 还在，不设置就不会调用。日常的中文稿由 `data/translations/` 提供，套用后状态是 `ai`。`summary_zh` 可以空着，只要有 `title_zh` 就会套用，空概要不会把已有概要清掉。

同一次定时任务还会刷新最近 7 天 X 视频直链。这一步需要 Actions 能装 `yt-dlp`，不需要密钥。X 收件箱的工作流另外需要 Chrome（工作流里会装）。

提交发生在 `main`（或你手动运行时所在的分支）上。GitHub Pages 如果选的是「从分支部署 / main / 根目录」，这次提交会触发重新部署，不需要单独的构建。

### 你需要在 GitHub 上点的设置

仓库合并到 `main` 之后，定时任务才会按默认分支上的工作流运行。请逐项确认：

1. **Pages**：Settings → Pages → Build and deployment → Source 选 **Deploy from a branch**，Branch 选 **main**，文件夹选 **/ (root)**，保存。  
   项目站地址会是 `https://<用户名>.github.io/odd-news/`。页面里的数据路径是相对的，不依赖域名根路径。
2. **Actions 可以写仓库**：Settings → Actions → General → Workflow permissions 选 **Read and write permissions**。工作流文件里已经写了 `contents: write`；如果仓库把工作流锁成只读，推送数据会 403。
3. **Actions 已启用**。新仓库有时要先打开 Actions 标签页，允许工作流运行。
4. 合并这个拉取请求。定时任务只认默认分支上的工作流文件。

不需要为翻译配密钥。`GITHUB_TOKEN` 由 Actions 自动注入，只用来提交数据。

不想要机器翻译时，用 `python scripts/fetch_news.py --no-fallback`。本地调试也可以加 `--no-enrich`（跳过补主图和摘要）或 `--no-models`。

## 来源

只抓印度媒体和印度子版。2026-11-08 核对过的窗口条数仍写在表里，那是当时一条 feed 的返回数，不是去重后的每日新增。

已经停抓、历史里也不再展示内容地区不是印度的条目：Oddity Central、All That's Interesting、Oddee、UPI Odd News、Atlas Obscura、Mirror Weird News、Daily Star Weird News、Irish Mirror Weird News、Metro Weird、Express Weird News、New York Post Weird But True、SoraNews24、Neatorama、LADbible Weird、UNILAD Weird、Reddit r/nottheonion、Reddit r/Offbeat。以前从这些来源抓到、但正文地区仍是印度的旧条目留着；以后不会再抓。

### 在用

| 来源 | 地址 | 窗口条数 |
| --- | --- | --- |
| Hindustan Times Trending | `https://www.hindustantimes.com/feeds/rss/trending/rssfeed.xml` | 32 |
| India Today Trending | `https://www.indiatoday.in/rss/1797650` | 20 |
| Times of India Viral News | `https://timesofindia.indiatimes.com/rssfeeds/59016670.cms` | 20 |
| NDTV Offbeat | 见下方说明 | 27 |
| Indian Express Trending | `https://indianexpress.com/section/trending/feed/` | 200 |
| News18 Viral | Google News：`site:news18.com/viral OR site:news18.com/buzz when:2d`，解回 news18.com | 43 |
| Times Now Viral | Google News：`site:timesnownews.com (viral OR bizarre OR offbeat) when:3d` | 100 |
| Republic World Viral | Google News：`site:republicworld.com (viral OR buzz OR offbeat) when:3d`，只保留 republicworld.com | 52（93 条里解开并核对域名的） |
| Reddit r/india | `https://www.reddit.com/r/india/new/.rss?limit=100` | 100 |
| Reddit r/IndiaSpeaks | `https://www.reddit.com/r/IndiaSpeaks/new/.rss?limit=100` | 99 |
| Reddit r/indiasocial | `https://www.reddit.com/r/indiasocial/new/.rss?limit=100` | 99 |
| X | 外面的任务写入 `data/x/inbox/YYYY-MM-DD.json`，见 `docs/x-schema.md` | — |

Reddit 使用固定的 User-Agent：`linux:odd-news-daily:1.0.0 (by /u/odd-news-daily)`。外链帖打开原文，站内自帖丢掉。不要把这个标识改成编程语言的默认值，否则会被拒绝。赞和评论数在云端 IP 上经常拿不到 Reddit 自己的 JSON（403），所以按帖子 id 和原文链接去 Arctic Shift 公开存档补，补不到的保持原样，不补 0。

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
| Zee News viral | 栏目 RSS 403；Google News 搜 viral / offbeat / bizarre 近 7 天是 0 条 | 没加 |
| Free Press Journal viral | `/rss`、`/viral/rss`、`/feed` 都不是 feed；`site:freepressjournal.in/(viral OR lifestyle)` 是 0 条 | 没拿整站新闻来凑 |
| Business Today offbeat | `site:businesstoday.in/offbeat` 和 visual stories 是 0 条。首页 RSS 是财经，不是怪闻栏 | 没加 |
| OpIndia / ThePrint | OpIndia 的 feed 是政治评论，没有 offbeat 栏。ThePrint 被验证页挡住 | 没加 |
| NDTV trending | `site:ndtv.com/trending when:2d` 是 0 条。Offbeat 仍用原来的 Google News 查询 | 没另加一栏 |

## 第一次抓取（2026-11-08）

在这台环境里跑了 `python scripts/fetch_news.py`。

- 21 个在用来源全部成功，0 个失败
- 去重后 **651** 条，其中 **587** 条有主图地址
- 最近几天（按文章发布时间的北京时间）：11 月 8 日 48 条（当天晚上的快照，还没过完）、11 月 7 日 76 条、11 月 6 日 86 条、11 月 5 日 56 条。feed 窗口里更早的稿件也按原日期归档了
- **GitHub Models 没有译成。** 本机没有 `GITHUB_TOKEN`。另外直接请求 `https://models.github.ai/inference/chat/completions` 得到 HTTP 200 和纯文本 `OK`，不是聊天补全。651 条都用机器翻译写成了中文，`translation_status` 为 `fallback`。工作流每天仍会先试 Models；模型恢复后，最近 7 天的「机翻」会被换成模型概要

每天真正的新增取决于来源当天发了多少。上面这几天大约是 50–90 条。Reddit、印度趋势和英国怪闻栏忙的时候会更高。脚本不会为了凑数去抓普通新闻版。

## 印度素材占比（加上新来源之后）

对比的是同一批最近几天、按北京时间归档的条目。加来源之前的数字来自当时 `main` 上的数据。

| 日期 | 之前 | 之后 |
| --- | --- | --- |
| 2026-11-08 | 26/53（49%） | 203/231（88%） |
| 2026-11-07 | 35/76（46%） | 191/232（82%） |
| 2026-11-06 | 20/86（23%） | 108/174（62%） |
| 2026-11-05 | 1/56（2%） | 24/79（30%） |
| 2026-11-04 | 0/37（0%） | 21/58（36%） |
| 2026-11-03 | 0/33（0%） | 19/52（37%） |

全库 1347 条上的标签数量：街头食物 21，卫生环境 12，交通火车 50，航空出行 40，诈骗骗局 11，影视神剧 38，婚俗宗教 155，商业套路 34，科技发明 21，军事政治 127，动物 60，犯罪法律 145，奇人奇事 70，科学发现 54，历史考古 36，健康医疗 48，其他 583。规则没命中的归到「其他」，其中很多是 Reddit 上的闲聊帖。

## 本地查看

```bash
python3 scripts/fetch_news.py
python3 scripts/ingest_x.py
python3 -m http.server 8765
```

浏览器打开 `http://127.0.0.1:8765/`。不要用 `file://` 打开，否则读不到 `data/`。

中文用系统字体（苹方、思源黑体、微软雅黑等），没有从 CDN 拉字体。

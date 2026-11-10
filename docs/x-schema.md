# X 收件箱格式

外面的任务（不在本仓库的 Actions 里，它自己有 X API）把原始 JSON 提交到：

`data/x/inbox/YYYY-MM-DD.json`

`YYYY-MM-DD` 是这批素材收集日的北京时间，不是每条帖子的发布时间。推到默认分支的这个路径会触发 **Ingest X inbox**。也可以在 Actions 里手动跑。

工作流会下载图片和头像、用 `yt-dlp -g` 解析视频直链（不把视频文件放进仓库）、渲染评论区长图，再写进当天的 `data/YYYY-MM-DD.json` 和 `data/search/YYYY-MM.json`。站点条目的 `id` 仍是规范化 URL 的 sha1 前 16 位，和 `data/translations/` 用的是同一个键。推文雪花 ID 放在 `x.post_id`，不要拿它当翻译键。

## 文件

对象，必有 `posts` 数组。也接受顶层就是数组，但请按下面的对象提交。

```json
{
  "date": "2026-11-10",
  "posts": []
}
```

## 每条帖子

只写真实从 API 读到的数字。没有的计数字段不要补 0。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 推文雪花 ID |
| `url` | string | 原帖，形如 `https://x.com/<user>/status/<id>` |
| `author` | object | `name`, `username`, `avatar_url`, `verified` |
| `created_at` | string | ISO UTC，例如 `2026-11-05T07:56:08.000Z` |
| `text` | string | 全文，不要截断 |
| `lang` | string 或 null | 语言代码；不知道就 `null` |
| `public_metrics` | object | 见下方 |
| `photos` | string[] | 图片 URL。没有就是 `[]` |
| `video_thumbnail` | string 或 null | 视频封面。没有视频就 `null` |
| `has_video` | bool | |
| `video_direct_url` | string | 可选。收集时拿到的 mp4 直链。工作流会先跑 `yt-dlp -g`，失败才用它 |
| `title_zh` | string | 中文标题 |
| `summary_zh` | string | 中文概要。可以和标题相同，也可以更长 |
| `tags` | string[] | 1 到 3 个，必须是站点已有标签。不在列表里的会被丢掉；一个都不留时，入库脚本用关键词规则补 |
| `replies` | object[] | 见下方。没有就 `[]` |

`public_metrics` 使用这些键（回复也用同一套）：

```json
{
  "reply_count": 7,
  "repost_count": 3,
  "like_count": 4,
  "quote_count": 0,
  "bookmark_count": 0,
  "impression_count": 1791
}
```

`author`：

```json
{
  "name": "The Press Secretary",
  "username": "PressSecretary7",
  "avatar_url": "https://pbs.twimg.com/profile_images/2111364443057561600/vZi6BnIy_normal.jpg",
  "verified": true
}
```

`replies[]`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 回复雪花 ID |
| `author` | object | 同上 |
| `text` | string | 全文 |
| `created_at` | string | ISO UTC |
| `public_metrics` | object | 同上。API 没给的键不要补 |
| `in_reply_to_id` | string 或 null | 父帖 ID。直接回复原帖时就是原帖 `id`；回复另一条回复时是那条回复的 `id` |

标签只允许：街头食物、卫生环境、交通火车、航空出行、诈骗骗局、影视神剧、婚俗宗教、商业套路、科技发明、军事政治、动物、犯罪法律、奇人奇事、科学发现、历史考古、健康医疗、其他。

## 例子

2026-11-10 的试跑已经按这个格式放在 `data/x/inbox/2026-11-10.json`。那批原始包只有一句中文，所以 `title_zh` 和 `summary_zh` 相同。`video_direct_url` 是试跑时拿到的直链。

```json
{
  "date": "2026-11-10",
  "posts": [
    {
      "id": "2118250999898882303",
      "url": "https://x.com/PressSecretary7/status/2118250999898882303",
      "author": {
        "name": "The Press Secretary",
        "username": "PressSecretary7",
        "avatar_url": "https://pbs.twimg.com/profile_images/2111364443057561600/vZi6BnIy_normal.jpg",
        "verified": true
      },
      "created_at": "2026-11-05T07:56:08.000Z",
      "text": "Indian police wrestle a giant rat in a crowded street.",
      "lang": null,
      "public_metrics": {
        "reply_count": 7,
        "repost_count": 3,
        "like_count": 4,
        "quote_count": 0,
        "bookmark_count": 0,
        "impression_count": 1791
      },
      "photos": [],
      "video_thumbnail": "https://pbs.twimg.com/amplify_video_thumb/2118250974997360640/img/1TsCt9gT80zsGn5q.jpg",
      "has_video": true,
      "video_direct_url": "https://video.twimg.com/amplify_video/2118250974997360640/vid/avc1/720x1280/uxgz6mbTN1TpmlCG.mp4",
      "title_zh": "印度警察街头用绳子制服巨型大鼠（班迪库鼠），网民争论是不是AI造假。",
      "summary_zh": "印度警察街头用绳子制服巨型大鼠（班迪库鼠），网民争论是不是AI造假。",
      "tags": ["动物", "奇人奇事"],
      "replies": [
        {
          "id": "2118330706921193841",
          "author": {
            "name": "Gandalf",
            "username": "leje5411",
            "avatar_url": "https://pbs.twimg.com/profile_images/2094534203064954880/zdjwXhBz_normal.jpg",
            "verified": false
          },
          "text": "@PressSecretary7 @grok Master Splinter?",
          "created_at": "2026-11-05T13:12:51.000Z",
          "public_metrics": {
            "reply_count": 1,
            "repost_count": 0,
            "like_count": 1,
            "impression_count": 33
          },
          "in_reply_to_id": "2118250999898882303"
        }
      ]
    }
  ]
}
```

入库脚本同时接受试跑包的旧字段名（`video.meta.preview_image_url`、`public_metrics.like` / `view`、`referenced_tweets`），但新提交请用上面的字段。

## 入库之后 AI 文件里有什么

`data/search/YYYY-MM.json` 的路径不变。X 条目多一个 `kind: "x"` 和 `x` 对象，图片地址是 GitHub Pages 上的绝对 URL：

- `x.text` 原文
- `x.photos` 图片
- `x.video_thumbnail` 封面
- `x.comments_image` 评论长图 PNG
- `x.video_url` 直链，会过期；`x.video_url_note` 写明这一点
- `x.post_url` 原帖
- `x.ytdlp_command` 形如 `yt-dlp https://x.com/.../status/...`
- `x.author`、`x.public_metrics`、`x.replies`
- `x.video_url_resolved_at` 上次解析时间

每天 07:00（北京时间）的抓取会把最近 7 天 X 条目的 `video_url` 再用 `yt-dlp -g` 解析一次。

# zsxq-mirror · 小菜鸡仓库

> 一个把"星球内容 + 站内 AI 总结 + 会员体系 + 在线支付"打通的 Django 内容站。
> 线上演示：**[bddog.cn](https://bddog.cn)** —— 量化投资笔记 + 盘后 AI 总结，每日更新。

[![Demo](https://img.shields.io/badge/Demo-bddog.cn-818cf8?style=flat-square&logo=django&logoColor=white)](https://bddog.cn)
[![Python](https://img.shields.io/badge/Python-3.12+-3776ab?style=flat-square&logo=python&logoColor=white)](#)
[![Django](https://img.shields.io/badge/Django-6.0+-092e20?style=flat-square&logo=django&logoColor=white)](#)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](#)

---

## ✨ 这个项目能做什么

- 🕸 **知识星球同步**：Cookie 登录 + Playwright 抓取最新帖子（含图片/附件），落 SQLite，幂等导入
- 🧠 **AI 盘后总结**：每篇帖子点开自动生成多维度结构化分析（核心观点 / 背景解读 / 事实核查 / 潜在影响 / 操作建议 / 推荐标的），底层 DeepSeek + 博查 Web Search 联网兜底
- 👤 **会员体系**：邮箱验证码注册（阿里云邮件推送）、邀请码续期、新注册 10 分钟免费试读、阶梯付费套餐
- 💳 **在线支付**：接入四方聚合支付（微信 / 支付宝），异步通知 + 同步回跳 + 前端轮询三路确保到账
- 🎨 **Notion / Linear 风格自定义 CSS**：深色玻璃拟态，零 Bootstrap，手机端完整适配
- 🔐 **试读墙**：未登录可看首页 20 篇，深处帖子自动引导付费

## 🌐 看效果

直接打开 **https://bddog.cn** —— 完整生产环境，每天爬虫自动同步，AI 总结实时调用。

新注册账号默认送 10 分钟全站试读，可以无门槛体验所有功能。

## 🛠 技术栈

| 层 | 选型 |
|---|---|
| Web | Django 6 · gunicorn · nginx |
| 数据 | SQLite（够用，平稳运行 1.9w 条帖子） |
| 爬虫 | Playwright（Chromium headless）+ requests |
| AI | DeepSeek Chat + 博查 Web Search |
| 邮件 | 阿里云邮件推送（SMTP 465 SSL） |
| 支付 | qwgua 四方聚合（MD5 签名 + POST JSON） |
| 前端 | 手写 CSS / 原生 JS / Bootstrap Icons（仅字体） |

## 📦 本地起步

```bash
git clone https://github.com/100kez/zsxq-mirror.git
cd zsxq-mirror

# 1. 装依赖
pip install -r requirements.txt
playwright install chromium  # 同步星球用,纯本地玩可跳

# 2. 复制并编辑 .env
cp .env.example .env
$EDITOR .env   # 填上 DEEPSEEK_API_KEY、SMTP、支付商户号等

# 3. 初始化数据库 + 导入示例帖子
python manage.py migrate
python manage.py import_zsxq_json data/sample.json
python manage.py createsuperuser

# 4. 起服务
python manage.py runserver 0.0.0.0:8000
```

访问 http://localhost:8000，用刚创建的超管账号登录后台 `/admin/` 加邀请码。

## 📂 项目结构

```
quant_project/
├── accounts/        用户、会员、邀请码、支付订单
├── posts/           帖子、标签、附件、AI 对话
├── syncer/          知识星球爬虫 + 数据修复脚本
├── content_sync/    Django 项目 settings/urls
├── templates/       全部模板,继承 base.html
├── static/css/      唯一一份 site.css(设计令牌 + 所有样式)
├── wolfsheep/       附带的「狼羊鸡菜」过河小工具(独立)
└── data/sample.json 示例数据
```

## 🔑 必要的外部服务

按需选用：

| 服务 | 用途 | 不配置的后果 |
|---|---|---|
| **DeepSeek** | AI 要点分析 | 帖子详情页无 AI 卡片 |
| **博查 Web Search** | AI 追问联网 | AI 追问仅基于帖子原文 |
| **阿里云邮件推送** | 注册验证码 | 没法注册新用户 |
| **qwgua 四方支付** | 会员购买 | 只能用邀请码开会员 |

## 🤝 关于内容版权

- 仓库本身 **不包含** 任何知识星球付费内容
- `data/sample.json` 是虚构示例
- 你部署后同步进自己数据库的内容，版权归原作者所有
- 项目作者只提供工具，**请在原作者授权下使用**

## 📜 License

MIT —— 代码随便用，部署、改造、二次发行都行。但请：

- 不要直接搬运 [bddog.cn](https://bddog.cn) 上的内容
- 不要把同步到的他人付费内容公开传播

## 🐶 关于站点

[bddog.cn](https://bddog.cn) 是一个量化投资笔记站，专注盘后总结、行业拐点、资金面观察。如果你也在二级市场摸爬滚打，欢迎来逛逛 —— 注册即送 10 分钟全站试读。

---

如果这个项目对你有帮助，**点个 ⭐ Star** 让更多人看到 🙏

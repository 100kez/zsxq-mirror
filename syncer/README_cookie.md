# 知识星球爬虫使用说明（Cookie 登录模式）

## 前置条件

已获得星球主授权，允许将内容同步到本站。

---

## 一、安装依赖

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

---

## 二、从浏览器复制 Cookie

1. 用 Chrome / Edge 打开并**登录** `https://wx.zsxq.com`
2. 按 `F12` 打开开发者工具
3. 切换到 **Application（应用程序）** 标签
4. 左侧展开 **Storage → Cookies → https://wx.zsxq.com**
5. 在右侧找到所有 Cookie 条目
6. 或者切换到 **Network** 标签，刷新页面，随便点一个请求，  
   在 **Headers → Request Headers** 中找到 `Cookie:` 这一行，  
   复制其右侧的完整内容（一整行字符串）

---

## 三、创建 Cookie 文件

```bash
# 确保目录存在
mkdir -p syncer/auth

# 创建文件（替换为你实际复制的 Cookie 内容）
# 文件内容格式：key1=value1; key2=value2; key3=value3
# 注意：整个内容在一行，不要换行
```

手动创建文件 `syncer/auth/zsxq_cookie.txt`，粘贴 Cookie 内容保存即可。

> **安全提示**  
> - 不要将该文件提交到 git（已在 `.gitignore` 中排除）  
> - 不要将 Cookie 内容发给任何人或输出到日志  
> - Cookie 通常有效期为数天到数周，失效后需重新获取

---

## 四、运行爬虫

```bash
# 在项目根目录执行
python syncer/crawl_zsxq_with_cookie.py
```

成功后输出文件路径：`data/zsxq_export_test.json`

---

## 五、将数据导入 Django

```bash
# 预览（不写入数据库）
python manage.py import_zsxq_json data/zsxq_export_test.json --dry-run

# 正式导入
python manage.py import_zsxq_json data/zsxq_export_test.json
```

导入支持幂等操作：同一条帖子（`source_post_id` 相同）重复导入只会更新，不会重复插入。

---

## 六、常见错误排查

### 错误：Cookie 文件不存在

```
[错误] Cookie 文件不存在：syncer/auth/zsxq_cookie.txt
```

**解决**：按第三节步骤创建文件。

---

### 错误：Cookie 格式不完整

```
[错误] Cookie 解析结果为空，请检查文件格式
```

**解决**：确认文件内容为一整行，格式为 `key1=val1; key2=val2; ...`，不要有多余的换行或空格。

---

### 错误：仍然跳转到登录页

```
[错误] 页面跳转至登录地址，Cookie 可能已失效
```

**解决**：
1. Cookie 已过期，重新从浏览器复制最新 Cookie
2. 确认复制的 Cookie 来自已登录状态的页面
3. 确认复制的是 `wx.zsxq.com` 的 Cookie，不是其他子域

---

### 警告：未提取到任何帖子

```
[warn] 未提取到任何帖子
```

**解决**：
1. 先排查登录问题（见上）
2. 知识星球可能改版，页面 class 名称变化  
   → 打开 `syncer/crawl_zsxq_with_cookie.py`  
   → 找到 `_JS_EXTRACT` 变量  
   → 将 `itemSelectors` 数组中的选择器换成当前页面实际的 class 名称  
   → 调试技巧：将脚本顶部 `HEADLESS = True` 改为 `HEADLESS = False`，本地运行可看到真实浏览器

---

### 错误：页面选择器变化

知识星球前端不定期更新，CSS class 名称可能变化。调试方法：

```bash
# 1. 先将脚本中 HEADLESS 改为 False（仅限本地机器，服务器无图形界面）
# 2. 运行脚本，观察浏览器窗口中的实际页面
# 3. 用 DevTools 审查帖子元素，找到实际 class 名称
# 4. 更新 _JS_EXTRACT 中的 itemSelectors 和子元素选择器
```

---

## 七、注意事项

- 本脚本限制最多抓取 **5 条**帖子（`MAX_POSTS = 5`）
- 每次滚动之间随机等待 **2-5 秒**，避免高频请求
- 不下载附件，只记录文件名和 URL
- 不破解任何接口，完全依赖合法的浏览器 Cookie 登录态

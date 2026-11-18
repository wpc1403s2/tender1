# DeepSeek 参数提取

后端从项目根目录及后端目录的 `.env` 读取 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`，后端目录优先，进程环境变量优先于文件。密钥仅在后端使用。修改配置后重启后端。

`app/schemas/extraction_fields.json` 来自提供的《二期字段.xlsx》Sheet1，保留 84 个非空条目及其说明，使用业务编号作为字段 ID。原工作簿没有修改，也不需要在运行时放置在服务器上。第二列的说明作为提取范围，不作为标书参数值。

上传后进入审阅台会自动调用 `POST /api/v1/tender/{project_id}/analyze`，后台按文档块分批调用 DeepSeek Chat Completions JSON 输出。页面通过 `GET /api/v1/tender/{project_id}/review` 轮询进度，状态依次为 `READY → EXTRACTING → EXTRACTED`，失败为 `FAILED`。未检出字段显示“未提及”，失败不会伪装为成功。“重新提取参数”支持重试；已有表格时提示将替换未保存的人工修改。

模型返回字段 ID、值、原文片段 ID 和引用文本。后端验证引用属于该请求的真实文档块，再从解析结果回填文件、页码和 BBox。失败引用自动请求纠正一次，仍无法验证则丢弃引用、标注字段“待核验”，保留其他有效结果。引用校验不能替代业务复核，模型仍可能漏提或归类错误。一个字段可有多个来源，点击页码可切换依据。Word/Excel 可参与提取，但当前原文预览仅支持 PDF。

解析快照存放在 `transformer-agent-backend/data/parsed`，提取结果存放在 `data/extractions`；两个目录均已忽略提交。原来只保留上传文件的项目会在首次打开时重新解析恢复。追加上传使旧提取结果失效。刷新页面或重启后端会读取成功结果，避免重复调用。当前任务运行在单个后端进程内，请使用一个 Uvicorn worker；提取期间重启会中断任务，重新进入页面或点击重新提取可恢复工作。尚未接入分布式任务队列。

本次实现右侧参数提取，不包含组部件 RAG 匹配、人工修改持久化和 Excel 导出。部署容器时需注入实际环境变量并挂载 data 目录；现有 compose 中的示例 API key 不能用于实际调用。

验证命令（在后端目录执行）：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_extraction.py -v
# 使用真实服务，会产生 API 用量；已有缓存时不重复调用，--force 强制重新提取
.venv/Scripts/python.exe -m tests.live_extraction proj_efd385ce --force
```

前端构建：在前端目录执行 `npm run build`。

接口参考：https://api-docs.deepseek.com/api/create-chat-completion/

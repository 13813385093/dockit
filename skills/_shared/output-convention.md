> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败。错误信息统一为 `ERROR [<错误码>] <原因>。修复：<建议>`，读到后直接按建议行动。
>
> 例外：`spec status` / `spec read` / `spec schema` 三个命令直接输出文本——`spec status` 是一行中文状态描述，`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。
>
> 未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `review` / `dev`）之前。

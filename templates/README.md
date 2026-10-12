# Alyrra 本地卡片模板

三套主题：forest 晨光歌林、starlight 月夜星河、stage 舞台花信。
assets/alyrra.jpg 是用户提供的角色形象原图，卡片完整展示，不由模型重绘。
每套支持签到和幸运签，两种版式共六张预览，见 previews/all_templates.png。

backgrounds 为预制 PNG 背景；themes.json 控制配色和主题文案。
cards.py 本地绘制徽记、边框、装饰和动态文字，不调用图片生成模型。
重新生成背景与预览：在项目根目录运行 .\.venv\Scripts\python.exe cards.py。

画布为1200×900。幸运签自动换行并根据长度调整字号，过长时回退文字发送，不截断签文。
默认使用 Windows 微软雅黑；其他系统须用 CARD_FONT 指定支持中文的 TTF/TTC 字体绝对路径。
不分发 Windows 字体文件。

生成的实际卡片位于 rendered_cards，最多保留100张；不提交含成员称呼的实际卡片。
previews 使用虚构示例数据，背景和示例可随项目一起发布。

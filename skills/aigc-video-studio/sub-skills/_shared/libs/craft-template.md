# CRAFT 提示词模板（设计稿 §6）

> 全技能统一基准：第零层去 AI 味基座 + 四层结构 + CRAFT 八要素校验。

## 第零层 · 去 AI 味基座（强制注入）

在四层结构**之前**强制注入，作为全片质感下限。词库见 `deai-keywords.yaml`（按风格分组）。`prompt_qc.py` 校验缺失则硬阻断。

```
正向强制词：超写实质感, 真实电影摄影, 胶片颗粒, 自然皮肤纹理/真实材质,
            真实光线衰减与阴影, 镜头呼吸/轻微手持感, 景深与焦外自然
反向强制词：no CG look, no plastic skin, no over-smooth/磨皮, no uncanny valley,
            no over-saturated AI colors, no waxy texture, no perfect symmetry
```

## 四层结构模板（视频提示词主模板）

```
【第零层 · 去AI味基座】<见上，按风格选 deai-keywords 组>

【第一层 · 基础设定】
角色：<从 CharacterCard.feature_card 原文注入，禁止改写>
场景：<场景关键词：地点/时代/天气/光线/关键道具>
声音：<audio_cue：环境音/音效氛围/有无对白>

【第二层 · 氛围与画质】
风格核心：<style-bible 主基调>
视觉基调：<影调/色彩>
美学参考：<导演/影片/器材锚点>

【第三层 · 分镜执行】
景别与构图：<shot_size + composition（坐标化写法）>
运镜：<camera_move 明确方向化表述>
画面内容：<action_logic：动作 + 动机/因果，留白处明确标注"由模型自由发挥">
```

## CRAFT 八要素校验公式

`[去AI味质感] + [主体] + [动作] + [背景/环境] + [视觉风格] + [相机/摄影] + [构图坐标] + [情绪/氛围]`

八要素齐备；**缺失任一即阻断出卡**（结构硬阻断，确定性无噪声）。LLM-as-Judge 在结构校验通过后再按八要素语义评分（0–100），仅排序/标红，不阻断。

八要素键名（供 `prompt_qc.py` 引用）：

```
deai_texture     # 去AI味质感
subject          # 主体
action           # 动作
environment      # 背景/环境
visual_style     # 视觉风格
camera           # 相机/摄影
composition      # 构图坐标
mood             # 情绪/氛围
```

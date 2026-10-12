"""固定背景素材与动态文字数据，本地渲染签到及幸运签。"""
import argparse
import asyncio
import base64
import json
import logging
import os
import random
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
from botpy.http import Route

ROOT = Path(__file__).resolve().parent
THEMES = json.loads((ROOT / 'templates' / 'themes.json').read_text(encoding='utf-8'))
W, H = 1200, 900
LOG = logging.getLogger('alyrra')


def font(size, bold=False):
    candidates = [os.getenv('CARD_FONT', ''), 'C:/Windows/Fonts/msyhbd.ttc' if bold else 'C:/Windows/Fonts/msyh.ttc',
                  '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
    for path in candidates:
        if path and Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise RuntimeError('缺少中文字体，请设置 CARD_FONT')


def rgb(value):
    return tuple(bytes.fromhex(value.lstrip('#')))


def background(theme):
    config = THEMES[theme]
    a, b = rgb(config['top']), rgb(config['bottom'])
    image = Image.new('RGB', (W, H))
    draw = ImageDraw.Draw(image)
    for y in range(H):
        color = tuple(round(a[i] + (b[i] - a[i]) * y / H) for i in range(3))
        draw.line((0, y, W, y), fill=color)
    accent = config['accent']
    rng = random.Random(theme)
    for _ in range(65):
        x, y = rng.randint(30, W-30), rng.randint(35, H-35)
        r = rng.choice([1, 1, 2, 3])
        draw.ellipse((x-r, y-r, x+r, y+r), fill=accent)
    draw.rounded_rectangle((26, 26, W-26, H-26), radius=32, outline=accent, width=2)
    draw.rounded_rectangle((40, 40, W-40, H-40), radius=26, outline=tuple(min(v+18,255) for v in a), width=1)
    # 固定月轮、琴弦、蝴蝶结徽记，不依赖不稳定的角色生成。
    draw.ellipse((80, 240, 355, 515), outline=accent, width=3)
    draw.ellipse((104, 264, 331, 491), outline=accent, width=1)
    if theme == 'forest':
        for x,y in [(118,348),(315,355),(110,435),(322,446)]:
            draw.ellipse((x-22,y-35,x+22,y+35),fill=accent)
        for x in (160,200,240,280):
            draw.line((x,560,x-45,720),fill=accent,width=2)
            draw.ellipse((x-50,620,x-10,644),outline=accent,width=2)
    elif theme == 'starlight':
        nodes=[(90,600),(150,650),(215,583),(290,660),(335,592)]
        draw.line(nodes,fill=accent,width=2)
        for x,y in nodes:
            draw.ellipse((x-6,y-6,x+6,y+6),fill=accent)
    else:
        for x in (95,155,215,275,335):
            draw.line((x,590,x,735),fill=accent,width=2)
            draw.ellipse((x-15,720,x+15,739),fill=accent)
    draw.polygon([(165,340),(217,375),(165,413)],fill=accent)
    draw.polygon([(275,340),(223,375),(275,413)],fill=accent)
    draw.ellipse((205,363,235,389),fill=accent)
    draw.text((82,90), 'ALYRRA',font=font(52,True),fill=accent)
    draw.text((84,164),config['subtitle'],font=font(18),fill=accent)
    draw.text((92,773),config['name'],font=font(30),fill=accent)
    draw.text((92,822),'精灵歌姬的日常手账',font=font(18),fill=accent)
    draw.rounded_rectangle((410,76,1128,824),radius=28,fill=config['paper'])
    return image


def clean(text):
    text=re.sub(r'[*#`]', '',str(text))
    return ''.join(c for c in text if ord(c)<0x10000 and c not in '\ufe0f\u200d').strip()


def lines(text, size, width):
    f=font(size)
    result=[]
    for paragraph in clean(text).split('\n'):
        line=''
        for char in paragraph:
            if f.getlength(line+char)>width and line:
                if char in '。，！？；：、）》」』】':
                    result.append(line+char);line=''
                else:
                    result.append(line);line=char
            else:
                line+=char
        result.append(line)
    return result


def render(kind, data, theme='forest', output=None):
    if theme not in THEMES or kind not in {'checkin','fortune'}:
        raise ValueError('未知卡片模板')
    path=ROOT/'templates'/'backgrounds'/f'{theme}.png'
    if path.exists():
        with Image.open(path) as source:
            image=source.convert('RGB')
    else:
        image=background(theme)
    draw=ImageDraw.Draw(image)
    ink=THEMES[theme]['top']
    portrait=ROOT/'templates'/'assets'/'alyrra.jpg'
    if portrait.exists():
        # 原图作为模板中的图片组件完整展示，不重绘角色。
        with Image.open(portrait) as source:
            avatar=source.convert('RGB')
            avatar.thumbnail((300,300),Image.Resampling.LANCZOS)
            x=68+(300-avatar.width)//2
            y=248+(300-avatar.height)//2
            draw.rounded_rectangle((60,240,376,556),radius=20,fill=THEMES[theme]['accent'])
            image.paste(avatar,(x,y))
    draw.text((456,112),'每日签到' if kind=='checkin' else '精灵幸运签',font=font(46,True),fill=ink)
    date=data.get('date') or datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y.%m.%d')
    draw.text((458,178),date+'  ·  ALYRRA JOURNAL',font=font(17),fill=ink)
    draw.line((458,222,1080,222),fill=ink,width=1)
    name=clean(data.get('name') or '森林旅人')
    while font(28).getlength(name)>590:
        name=name[:-2]+'…'
    draw.text((458,252),name,font=font(28,True),fill=ink)
    if kind=='checkin':
        points,streak=int(data['points']),int(data['streak'])
        draw.text((458,312),'签到成功 · 星光 +10' if data.get('added') else '今日已签到 · 星光已领取',font=font(24),fill=ink)
        for x,label,value in [(458,'歌林星光',str(points)),(802,'连续签到',str(streak)+' 天')]:
            draw.rounded_rectangle((x,380,x+280,525),radius=18,outline=ink,width=1)
            draw.text((x+23,399),label,font=font(19),fill=ink)
            draw.text((x+23,442),value,font=font(40,True),fill=ink)
        rank='星河听众' if points>=300 else '练歌伙伴' if points>=100 else '森林访客'
        target=300 if points>=100 else 100
        draw.text((458,561),'当前称号  '+rank,font=font(26,True),fill=ink)
        draw.rounded_rectangle((458,620,1082,634),radius=7,fill='#D8D7DA')
        width=max(14,int(624*min(points/target,1)))
        draw.rounded_rectangle((458,620,458+width,634),radius=7,fill=ink)
        progress='已解锁全部称号' if points>=300 else f'下一称号还需 {target-points} 星光'
        draw.text((458,653),progress,font=font(20),fill=ink)
        draw.text((458,744),'哼，今天也记得来听本精灵唱歌呀。',font=font(22),fill=ink)
    else:
        body=data['text']
        for size in range(30,17,-1):
            wrapped=lines(body,size,620)
            if len(wrapped)*(size+12)<=435:
                break
        else:
            raise ValueError('签文过长，回退文字')
        for i,line in enumerate(wrapped):
            draw.text((458,315+i*(size+12)),line,font=font(size),fill=ink)
        draw.text((458,775),'随心抽签 · 娱乐创作',font=font(17),fill=ink)
    folder=ROOT/'rendered_cards'
    folder.mkdir(exist_ok=True)
    output=Path(output) if output else folder/(uuid4().hex+'.png')
    image.save(output)
    if output.parent==folder:
        for old in sorted(folder.glob('*.png'),key=lambda p:p.stat().st_mtime)[:-100]:
            old.unlink(missing_ok=True)
    return output


async def send(chat,msg,kind,data):
    if not chat.settings.get('cards_enabled',True):
        return False
    setting=chat.settings.get('card_theme','random')
    theme=random.choice(list(THEMES)) if setting=='random' else setting
    try:
        path=await asyncio.to_thread(render,kind,data,theme)
        media=await asyncio.wait_for(chat.bot.api._http.request(
            Route('POST','/v2/groups/{group_openid}/files',group_openid=msg.group_openid),
            json={'file_type':1,'file_data':base64.b64encode(path.read_bytes()).decode('ascii'),'srv_send_msg':False}),timeout=30)
        if not media.get('file_info'):
            raise RuntimeError('QQ 未返回 file_info')
        await msg.reply(msg_type=7,media={'file_info':media['file_info']})
        return True
    except Exception as exc:
        LOG.warning('卡片渲染或发送失败：%s，回退文字。',type(exc).__name__)
        return False


def build_previews():
    folder=ROOT/'templates'/'backgrounds'
    folder.mkdir(exist_ok=True)
    preview=ROOT/'templates'/'previews'
    preview.mkdir(exist_ok=True)
    samples=[]
    for theme in THEMES:
        background(theme).save(folder/f'{theme}.png')
        for kind,data in [('checkin',dict(name='歌林旅人',points=170,streak=7,added=True)),
                          ('fortune',dict(name='歌林旅人',text='签名：星河回响\n\n签文：微弱的碎光，也能汇聚成属于你的旋律。今天不必急着抵达，先听一听心里的声音。\n\n小行动：给自己留十分钟，听一首喜欢的歌。\n幸运颜色：极光紫'))]:
            path=render(kind,data,theme,preview/f'{theme}_{kind}.png')
            with Image.open(path) as img:
                samples.append(img.resize((600,450)))
    sheet=Image.new('RGB',(1800,900),'white')
    for i,img in enumerate(samples):
        sheet.paste(img,((i//2)*600,(i%2)*450))
    sheet.save(preview/'all_templates.png')


if __name__=='__main__':
    build_previews()

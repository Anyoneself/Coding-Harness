#!/usr/bin/env python3
"""Legacy educational implementation.

从零实现中文 Word2Vec Skip-gram Embedding
══════════════════════════════════════════
仅用 NumPy (jieba 可选), 判断两个中文词语义是否相近

核心思想:
  语义相近的词 → 出现在相似的上下文 → 训练后向量接近

模型结构:
  中心词 → [查表 W] → 嵌入 h → [矩阵乘 C] → softmax → 预测上下文词
"""

import numpy as np
from collections import Counter

# ── jieba 可选, 不装就用逐字切分 ──
try:
    import jieba
    jieba.setLogLevel(jieba.logging.WARNING)
    _JIEBA = True
except ImportError:
    _JIEBA = False

_STOP = set(
    "的 了 在 是 我 有 和 就 不 人 都 一 上 也 很 到 说 要 去 你 会 着 "
    "没 看 好 这 那 他 她 它 们 把 被 让 给 对 从 但 而 因 所 如 么 吗 吧 呢 "
    "可以 一个 没有 自己 什么 这个 那个 时候 地方 每天 需要".split()
)


class Word2Vec:
    """Skip-gram Word2Vec ── 纯 NumPy 实现"""

    def __init__(self, dim=100, window=4, lr=0.025, epochs=200, min_count=1):
        self.dim, self.window = dim, window
        self.lr, self.epochs, self.min_count = lr, epochs, min_count

    def _tokenize(self, text):
        if _JIEBA:
            return [w.strip() for w in jieba.lcut(text)
                    if w.strip() and w.strip() not in _STOP]
        return [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]

    def fit(self, sentences):
        # ── 1. 词表 ──
        freq = Counter()
        for s in sentences:
            freq.update(self._tokenize(s))
        self.w2i, self.i2w, idx = {}, {}, 0
        for w, c in freq.most_common():
            if c >= self.min_count:
                self.w2i[w] = idx; self.i2w[idx] = w; idx += 1
        self.V = len(self.w2i)
        print(f"分词方式 : {'jieba 词级切分' if _JIEBA else '逐字切分 (建议 pip install jieba)'}")
        print(f"词表大小 : {self.V}")

        # ── 2. Skip-gram 训练对 ──
        pairs = []
        for s in sentences:
            ids = [self.w2i[w] for w in self._tokenize(s) if w in self.w2i]
            for i, cen in enumerate(ids):
                r = np.random.randint(1, self.window + 1)
                for j in range(max(0, i - r), min(len(ids), i + r + 1)):
                    if j != i:
                        pairs.append((cen, ids[j]))
        print(f"训练对数 : {len(pairs)}")

        # ── 3. 初始化权重 ──
        sc = 1.0 / self.dim
        self.W = np.random.uniform(-sc, sc, (self.V, self.dim))   # 输入嵌入
        self.C = np.random.uniform(-sc, sc, (self.dim, self.V))   # 输出权重

        # ── 4. SGD 训练 ──
        for ep in range(1, self.epochs + 1):
            np.random.shuffle(pairs)
            loss = 0.0
            cur_lr = self.lr * (1 - ep / (self.epochs + 1))
            with np.errstate(invalid='ignore', divide='ignore', over='ignore'):
                for cen, ctx in pairs:
                    h = self.W[cen]
                    z = h @ self.C
                    np.clip(z, -50, 50, out=z)        # 防止 exp 溢出
                    z -= z.max()
                    p = np.exp(z);   p /= p.sum()
                    loss -= np.log(p[ctx] + 1e-12)
                    g = p.copy();  g[ctx] -= 1.0
                    self.W[cen] -= cur_lr * (self.C @ g)
                    self.C      -= cur_lr * np.outer(h, g)
            # 安全兜底：重置 NaN/Inf 权重
            bad_w = ~np.isfinite(self.W)
            bad_c = ~np.isfinite(self.C)
            if bad_w.any() or bad_c.any():
                self.W[bad_w] = np.random.uniform(-sc, sc, bad_w.sum())
                self.C[bad_c] = np.random.uniform(-sc, sc, bad_c.sum())
            if ep == 1 or ep % max(1, self.epochs // 10) == 0:
                print(f"  epoch {ep:4d}/{self.epochs}  loss={loss / len(pairs):.4f}")

        norms = np.linalg.norm(self.W, axis=1, keepdims=True)
        self.Wn = self.W / np.where(norms < 1e-8, 1, norms)
        print("训练完成!\n")

    def __contains__(self, w):
        return w in self.w2i

    def vector(self, word):
        return self.W[self.w2i[word]]

    def similarity(self, a, b):
        """余弦相似度 (-1 ~ 1), 越大越相似"""
        va, vb = self.W[self.w2i[a]], self.W[self.w2i[b]]
        return float(va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb)))

    def most_similar(self, word, topn=5):
        """返回最相似的 topn 个词"""
        if word not in self.w2i:
            return []
        v = self.Wn[self.w2i[word]]
        with np.errstate(invalid='ignore', divide='ignore', over='ignore'):
            sims = self.Wn @ v
        sims[self.w2i[word]] = -2
        idxs = np.argsort(sims)[::-1][:topn]
        return [(self.i2w[i], float(sims[i])) for i in idxs]


# ═══════════════════════════════════════════════
#  中文语料库 & 演示
# ═══════════════════════════════════════════════

if __name__ == "__main__":

    corpus = [
        # ─────── 动物 ───────
        "猫是一种很可爱的宠物",
        "狗是一种很忠诚的宠物",
        "小猫在沙发上安静地睡觉",
        "小狗在院子里开心地玩耍",
        "猫喜欢吃小鱼干",
        "狗喜欢吃肉骨头",
        "猫和狗都是人类的好朋友",
        "我家养了一只猫非常可爱",
        "我家养了一只狗非常听话",
        "宠物猫的毛很柔软很舒服",
        "宠物狗的毛也很柔软很舒服",
        "猫是比较高冷安静的动物",
        "狗是比较热情活泼的动物",
        "猫咪喜欢在温暖的阳光下打盹",
        "狗狗喜欢在草地上开心地奔跑",
        "那只猫长得真漂亮",
        "那只狗长得真威风",
        "猫会用爪子给自己洗脸",
        "狗会摇尾巴来表示开心",
        "猫和兔子都是可爱的小动物",
        "狗和猫都可以陪伴孤独的人",
        "兔子的耳朵又长又可爱",
        "小兔子蹦蹦跳跳地很活泼",
        "鸟儿站在树枝上快乐地唱歌",
        "金鱼在鱼缸里自由地游来游去",

        # ─────── 食物 ───────
        "米饭是中国人最常吃的主食",
        "面条是北方人最喜欢的主食",
        "馒头也是北方人常吃的主食",
        "米饭搭配炒菜吃非常香",
        "面条搭配各种汤汁非常美味",
        "馒头搭配酱料吃也很不错",
        "我每天都吃米饭当主食",
        "我每天都吃面条当早餐",
        "饺子是中国传统经典美食",
        "包子是中国传统经典面食",
        "饺子的馅料种类非常丰富",
        "包子的馅料种类也非常丰富",
        "过年全家人一起包饺子",
        "早餐吃几个热腾腾的包子",
        "煮一锅热腾腾的饺子当晚餐",
        "蒸一笼香喷喷的包子当早餐",
        "米饭搭配红烧肉简直绝配",
        "面条搭配炸酱简直绝配",
        "吃饺子要蘸醋才够味",
        "米饭是南方人餐桌上的最爱",
        "面条是北方人餐桌上的最爱",
        "做一锅米饭非常简单方便",
        "煮一碗面条也非常简单方便",
        "苹果是一种常见的水果",
        "香蕉是一种好吃的水果",
        "苹果和香蕉都是很有营养的水果",
        "多吃新鲜水果对身体很有好处",

        # ─────── 运动 ───────
        "足球是世界上最受欢迎的运动",
        "篮球是世界上很受欢迎的运动",
        "踢足球需要很好的体力和耐力",
        "打篮球需要很好的体力和弹跳",
        "足球是一项需要团队配合的运动",
        "篮球也是一项需要团队配合的运动",
        "世界杯是最盛大的足球比赛",
        "篮球联赛也是非常精彩的比赛",
        "我喜欢在宽阔的操场上踢足球",
        "我喜欢在篮球场上打篮球",
        "看足球比赛看得非常过瘾",
        "看篮球比赛看得非常刺激",
        "踢足球可以很好地锻炼身体",
        "打篮球也可以很好地锻炼身体",
        "周末约好朋友一起去踢足球",
        "周末约好朋友一起去打篮球",
        "足球进球的那一刻最让人激动",
        "篮球投中的那一刻最让人兴奋",
        "游泳是一项非常好的运动项目",
        "跑步是最简单有效的运动方式",
        "坚持游泳可以增强全身的力量",
        "坚持跑步可以增强心肺的功能",
        "我每天早晨去游泳池游泳",
        "我每天傍晚去公园里跑步",
        "游泳和跑步都是有氧运动",
        "经常运动可以让人保持健康",
        "足球场上的竞争非常激烈",
        "篮球场上的对抗也非常激烈",

        # ─────── 家庭 ───────
        "爸爸是家里最坚强的顶梁柱",
        "妈妈是家里最温柔的港湾",
        "爸爸每天在外面辛苦地工作",
        "妈妈每天在家里辛苦地忙碌",
        "爸爸对我的爱是非常深沉的",
        "妈妈对我的爱是非常温暖的",
        "我从小就非常爱我的爸爸",
        "我从小就非常爱我的妈妈",
        "爸爸经常带我去公园里玩",
        "妈妈经常带我去超市买东西",
        "爸爸教会了我骑自行车",
        "妈妈教会了我做很多事",
        "哥哥从小就是我的好榜样",
        "姐姐从小就是我的好伙伴",
        "哥哥比我大很会照顾人",
        "姐姐比我大也很会关心人",
        "哥哥经常带我一起去运动",
        "姐姐经常带我一起去看书",
        "爸爸和妈妈都非常疼爱我",
        "哥哥和姐姐都非常爱护我",
        "家人永远是我最温暖的依靠",
        "全家人一起吃饭是最幸福的时光",
        "过节的时候全家人欢聚一堂",
        "爷爷喜欢在院子里晒太阳",
        "奶奶喜欢给我们做好吃的",
        "爷爷和奶奶年纪大了要多关心",

        # ─────── 学习 ───────
        "老师在明亮的教室里认真讲课",
        "学生在明亮的教室里认真听课",
        "老师把丰富的知识传授给学生",
        "学生努力地学习各种新的知识",
        "好的老师会影响学生的一辈子",
        "好的学生都非常尊敬自己的老师",
        "上课的时候要集中注意力听课",
        "下课以后要及时认真地做作业",
        "课本是学生学习知识的重要工具",
        "教室是学生学习知识的重要地方",
        "学校的图书馆里有各种各样的书",
        "学校的操场上可以做各种运动",
        "老师特别表扬了认真学习的同学",
        "学生非常感谢辛勤付出的老师",
        "数学老师讲课讲得非常有趣",
        "语文老师讲课讲得非常生动",
        "只有努力学习才能取得好成绩",
        "只有认真听讲才能学到更多",
        "学习是一件非常快乐的事情",
        "丰富的知识可以改变人的命运",
        "老师就像黑暗中指路的明灯",
        "学习要持之以恒不能三天打鱼",
        "多读书可以极大地开阔人的视野",

        # ─────── 天气 / 自然 ───────
        "今天天气晴朗阳光明媚",
        "明天可能会下一场大雨",
        "晴天的时候人的心情也会很好",
        "雨天的时候最适合在家里休息",
        "冬天下雪的时候世界变得很美",
        "春天到了花儿都盛开了",
        "夏天天气非常炎热要注意防暑",
        "秋天气温凉爽非常适合出游",
        "冬天天气非常寒冷要多穿衣服",
        "外面刮很大的风要注意保暖",
        "下雨了出门记得要带雨伞",
        "今天气温很高要注意多喝水",
        "春天万物复苏一片生机勃勃",
        "夏天可以去游泳来消暑降温",
        "秋天的树叶变成了金黄色",
        "冬天可以打雪仗堆雪人玩",
        "苹果好吃",
        "苹果和香蕉好吃",
        "苹果真好吃",
        "苹果和香蕉好吃",
        "苹果的好吃",
        "苹果，好吃",
        "苹果。好吃",
    ]

    # ────────── 训练 ──────────
    model = Word2Vec(dim=256, window=4, lr=0.01, epochs=1000, min_count=2)
    model.fit(corpus)

    # ────────── 展示结果 ──────────
    bar = "═" * 56

    # 实验 1: 相似词对 vs 不相关词对
    print(f"{bar}")
    print("  对比实验: 语义相近的词 vs 语义不相关的词")
    print(bar)
    tests = [
        ("猫",  "狗",    "猫",  "好吃"),
        ("米饭","面条",  "米饭","足球"),
        ("足球","篮球",  "足球","妈妈"),
        ("爸爸","妈妈",  "爸爸","游泳"),
        ("老师","学生",  "老师","面条"),
        ("苹果","香蕉",  "苹果","好吃"),
        ("游泳","跑步",  "游泳","包子"),
        ("哥哥","姐姐",  "哥哥","苹果"),
    ]
    ok_cnt = 0
    for a, b, c, d in tests:
        if a in model and b in model and c in model and d in model:
            s1 = model.similarity(a, b)
            s2 = model.similarity(c, d)
            ok = s1 > s2
            ok_cnt += ok
            print(f"  sim({a}, {b}) = {s1:+.4f}   vs   "
                  f"sim({c}, {d}) = {s2:+.4f}   {'[OK]' if ok else '[FAIL]'}")
    print(f"\n  >>> 准确率: {ok_cnt}/{len(tests)} 对通过\n")

    # 实验 2: 最相似词查询
    print(f"{bar}")
    print("  找出与目标词最相似的 5 个词")
    print(bar)
    queries = ["猫", "米饭", "足球", "爸爸", "老师", "游泳", "苹果"]
    for w in queries:
        if w in model:
            top = model.most_similar(w, 5)
            items = ", ".join(f"{word}({s:.3f})" for word, s in top)
            print(f"  {w}  ->  {items}")
        else:
            print(f"  {w}  ->  [不在词表中]")

    print(f"\n{bar}")
    print("  自由查询 (可自行修改)")
    print(bar)
    print(f"  model.similarity('猫', '狗')  = {model.similarity('猫', '狗'):.4f}")
    print(f"  model.similarity('猫', '篮球')= {model.similarity('猫', '篮球'):.4f}")

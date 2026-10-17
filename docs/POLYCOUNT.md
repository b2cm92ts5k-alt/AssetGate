# Polygon count ranges (m1-16) · ช่วงจำนวนโพลีกอน

[Manual (EN)](MANUAL.en.md#m1-16-polygon-count-fits-the-work--confirmable-advice-not-a-rule) · [คู่มือ (TH)](MANUAL.th.md#m1-16-จำนวนโพลีกอนเหมาะกับงาน--ยืนยันได้-คำแนะนำ-ไม่ใช่กฎ)

**There is no official standard** — the Unity Asset Store sets no polygon limit. These are common industry ranges in triangles per model, kept in `config.polycount` so you can change them for your game.

**ไม่มีมาตรฐานทางการ** — Unity Asset Store ไม่ได้กำหนดจำนวนโพลีกอน ตัวเลขด้านล่างเป็นช่วงที่ใช้กันทั่วไปในวงการ (หน่วยเป็นสามเหลี่ยมต่อชิ้น) เก็บไว้ใน `config.polycount` แก้ให้ตรงกับเกมของคุณได้

## General levels · ระดับทั่วไป

| Triangles · สามเหลี่ยม | Level · ระดับ |
|---|---|
| ≤ 1,500 | Low poly · โพลีต่ำ |
| ≤ 10,000 | Mid poly · โพลีกลาง |
| ≤ 100,000 | High poly for games · โพลีสูงสำหรับเกม |
| more · มากกว่านั้น | Very high, not game-ready yet · สูงมาก ยังไม่พร้อมใช้ในเกม |

Sources: Unity forum threads on low / mid / high poly, Polycount community.

## By model type · ตามประเภทโมเดล

| Type · ประเภท | Mobile | PC |
|---|---|---|
| Small prop · พร็อพชิ้นเล็ก | 50 – 500 | 100 – 1,500 |
| Medium prop · พร็อพชิ้นกลาง | 300 – 2,000 | 1,000 – 6,000 |
| Building / large piece · สิ่งก่อสร้าง/ชิ้นใหญ่ | 500 – 4,000 | 2,000 – 15,000 |
| Tree / foliage · ต้นไม้ / พืช | 300 – 2,500 | 1,500 – 8,000 |
| Main character · ตัวละครหลัก | 2,000 – 8,000 | 8,000 – 30,000 |
| NPC / enemy · NPC / ศัตรู | 1,000 – 5,000 | 3,500 – 16,500 |
| Vehicle · ยานพาหนะ | 2,000 – 8,000 | 12,000 – 60,000 |
| Close-up hero object · ของชิ้นเด่น (ดูใกล้) | 2,000 – 8,000 \* | 5,000 – 20,000 |

**VR** uses the Mobile ranges, plus a whole-scene budget per frame: Quest 2 < 750,000 · Quest 3 < 1,500,000 triangles.
**VR** ใช้ช่วงของ Mobile และมีงบทั้งฉากต่อเฟรม: Quest 2 < 750,000 · Quest 3 < 1,500,000 สามเหลี่ยม

Sources:
- Type × Mobile/PC: lowpoly3d.com, "Low-poly polygon budgets for mobile/WebGL/console"
- NPC on PC: CryEngine documentation, "Character Budgets"
- Vehicle on PC: commercial vehicle packs (LOD0 around 12–15K) up to console racing-game cars (around 60K)
- Foliage on PC: Unity forum and tree packs on the Unreal Marketplace
- VR scene budget: Meta, device optimization comparison for Quest
- \* Hero object on mobile has no direct source; it uses the same range as main characters and vehicles on mobile · ไม่มีแหล่งโดยตรง ใช้ช่วงเดียวกับตัวละครหลักและยานพาหนะบนมือถือ

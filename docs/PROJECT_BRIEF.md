# Project brief

## Ідентифікація

- Тема: 25
- Назва: Real-time Mapping with Foundation Models
- Напрями: 3D Computer Vision, Foundation Models, SLAM
- Стейкхолдери з proposal: УКУ, Максим Жук, Басистий Олег

## Початкова ціль

Інтегрувати сучасні foundation models у pipeline real-time створення карти середовища зі спостережень агента та порівняти систему з класичним feature-based підходом за точністю й швидкістю.

## Початковий задум

Mapping будує карту невідомого середовища зі спостережень агента. Класичний підхід знаходить і зіставляє features між кадрами, тріангулює sparse 3D points та оцінює рух камери, але може втрачати tracking за слабкої текстури, blur або значних змін viewpoint.

Foundation geometry models (у proposal: DUSt3R, MASt3R, VGGT) можуть напряму оцінювати багатовидову 3D-геометрію, correspondences, depth або cameras. Monocular metric-depth models (Depth Anything 3, UniDepth, Metric3D) можуть дати dense depth і потенційно метричний масштаб. Семантичні backbones (DINO, SAM, CLIP) можуть перетворити геометричну карту на open-vocabulary map.

## Очікуваний результат з proposal

- відтворюваний mapping pipeline;
- benchmark проти класичного baseline;
- порівняння точності карти, FPS/latency та споживання пам'яті;
- demo.

## Уточнення для реалізації

Початковий proposal поєднує три великі задачі: pose estimation/SLAM, dense geometry і semantics. Для реалістичного семестрового виконання роботу поділено:

1. **MVP:** classical sparse SLAM + одна metric-depth/geometry model + scale/Sim(3) alignment + dense point-cloud fusion + benchmark.
2. **Stretch 1:** окреме порівняння з end-to-end multi-view model (DUSt3R/VGGT).
3. **Stretch 2:** semantic/open-vocabulary layer.

Це не змінює research goal; це встановлює перевірюваний критичний шлях.

## Уточнення про scale

Фрази «scale невідомий» і «metric scale відомий» стосуються різних виходів:

- monocular sparse SLAM зазвичай повертає trajectory/map в умовних одиницях — global scale невідомий;
- metric-depth model заявляє depth у метрах, але на новому domain може мати bias;
- завдання alignment — оцінити перетворення зі SLAM units у metric frame та перевірити його без використання held-out ground truth для fitting;
- якщо dense geometry model має власні cameras/coordinate frame, одного scale недостатньо — потрібен Sim(3).

Саме тому в benchmark окремо показуються raw metric depth, recovered scale, Sim(3)-aligned diagnostic і metric error без прихованого median scaling.

## Критерій успіху

Проєкт успішний, якщо команда може відтворити baseline і proposed pipeline, виміряти їх на однакових даних/hardware та зробити обґрунтований висновок. Позитивне покращення не гарантується: якісно проаналізований negative result також валідний, якщо pipeline, метрики й failure analysis відтворювані.

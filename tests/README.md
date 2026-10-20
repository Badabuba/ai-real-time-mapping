# Tests

Перший набір тестів має покривати:

1. back-project → project round trip;
2. відновлення відомого scalar scale з outliers;
3. відновлення synthetic Sim(3) з outliers;
4. transform direction і pose inversion;
5. resize/crop intrinsics update;
6. serialization round trip для data contracts;
7. smoke pipeline на малому fixture без великих model weights.

GPU/model integration tests позначаються окремо й не повинні бути єдиними тестами correctness.

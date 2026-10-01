from pathlib import Path
import hashlib,json
R=Path(__file__).parent/'reference'
expected={
'S3_MASTER_A_LV_CONT_GOLDEN_TRADES.csv':'3b5d55c7404d0e0eefa32d86cd5e773ed5187a8d9eca438c7cbb4718eceb11d6',
'S3_B_QUALITY_GOLDEN_TRADES.csv':'8106ce206422bb68270aadc1495e044dd3d447f5855e2d5cd970707d21937635',
'S3_MASTER_C_HV200_FADE_GOLDEN_TRADES.csv':'a4e1bc1c54e150d7733cedd5a7ebeca2b172695db7c6d11fba44bdd5f6fc10b2',
'S3_D_EXTREME_HV_GOLDEN_TRADES.csv':'55443790041afa23c5b70bdd4bb4ec5f4089d42b2c32fcc2a72df1f287fdfce9'}
ok=True
for f,want in expected.items():
 p=R/f;got=hashlib.sha256(p.read_bytes()).hexdigest();print(f,got,'OK' if got==want else 'MISMATCH');ok &= got==want
raise SystemExit(0 if ok else 1)

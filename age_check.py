#!/usr/bin/env python3
"""Estime si une personne detectee est un mineur, et construit l'image d'alerte.

⚠️ Ce script tourne dans le venv ~/pytorch-env (paddle + opencv), PAS dans le python
systeme du pipeline (qui utilise pyds/DeepStream). Il est appele en SOUS-PROCESSUS
par terrace_alert.py, precisement pour que les deux environnements ne se melangent pas.

Modele : PP-Human StrongBaseline (Baidu), entraine sur PA-100K = 598 vraies cameras
de surveillance. Il n'a PAS besoin de voir le visage : il lit la silhouette entiere.
Sortie n°21 du modele = probabilite "moins de 18 ans".

Tourne sur CPU (~500 ms) : le GPU reste entierement a DeepStream.

Usage :
    python3 age_check.py <image.jpg> <x1> <y1> <x2> <y2> <sortie.jpg>
Sortie sur stdout, une seule ligne :
    <score> <MINEUR|adulte|INDETERMINE> <hauteur_px>
"""
import os
import sys

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, 'models', 'strongbaseline_r50_30e_pa100k')

SEUIL_MINEUR = 0.5
# En dessous de cette hauteur, ni le modele ni l'oeil humain ne sont fiables.
# Mesure du 2026-09-06 sur 365 personnes de la zone terrasse :
#   < 100 px -> 10.6 % notees "mineur"   |   >= 100 px -> 1.1 %
# et la vignette est un pate flou. On alerte quand meme (une personne est une
# personne) mais SANS annoncer d'age.
HAUTEUR_MIN_FIABLE = 100

IDX_AGE_LESS_18 = 21          # index dans les 26 attributs du modele
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)

# Zone piscine, dessinee sur l'image d'alerte pour situer la scene.
# ⚠️ Doit rester coherent avec roi-POOL dans configs/config_nvdsanalytics.txt
POOL_POLYGON = [(843, 223), (1402, 400), (1154, 572), (593, 302)]


def score_mineur(image_path, box):
    """Probabilite que la personne dans `box` ait moins de 18 ans (0.0 a 1.0)."""
    import cv2
    import paddle
    paddle.set_device('cpu')
    from paddle import inference

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(image_path)
    h, w = img.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    crop = img[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    if crop.size == 0:
        return None

    im = cv2.resize(crop, (192, 256)).astype(np.float32) / 255.0
    im = ((im[:, :, ::-1] - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)

    cfg = inference.Config(f'{MODEL_DIR}/model.pdmodel', f'{MODEL_DIR}/model.pdiparams')
    cfg.disable_gpu()                 # le GPU est pris par DeepStream
    cfg.disable_glog_info()
    cfg.set_cpu_math_library_num_threads(4)
    pred = inference.create_predictor(cfg)

    ih = pred.get_input_handle(pred.get_input_names()[0])
    oh = pred.get_output_handle(pred.get_output_names()[0])
    ih.reshape(im.shape)
    ih.copy_from_cpu(im)
    pred.run()
    return float(oh.copy_to_cpu()[0][IDX_AGE_LESS_18])


def build_alert_image(image_path, box, out_path, zoom=3.2):
    """Vue LARGE autour de la personne, pas un gros plan.

    Un recadrage serre sur une personne de 56 px est un pate illisible (teste).
    Ici : la personne est encadree en rouge, la zone piscine tracee en bleu, et on
    garde le contexte autour -> la situation se juge en 2 secondes sur un telephone.
    """
    import cv2
    img = cv2.imread(image_path)
    if img is None:
        return None
    H, W = img.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    ww = max(int((x2 - x1) * zoom), 520)
    hh = max(int((y2 - y1) * zoom), 400)
    X1, Y1 = max(0, cx - ww // 2), max(0, cy - hh // 2)
    X2, Y2 = min(W, X1 + ww), min(H, Y1 + hh)
    X1, Y1 = max(0, X2 - ww), max(0, Y2 - hh)

    pts = np.array(POOL_POLYGON, np.int32)
    over = img.copy()
    cv2.fillPoly(over, [pts], (255, 190, 60))
    img = cv2.addWeighted(over, 0.16, img, 0.84, 0)
    cv2.polylines(img, [pts], True, (255, 190, 60), 3)
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)

    crop = img[Y1:Y2, X1:X2]
    if crop.size == 0:
        crop = img
    if max(crop.shape[:2]) < 900:
        s = 900 / max(crop.shape[:2])
        crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    cv2.imwrite(out_path, crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return out_path


def main():
    image_path = sys.argv[1]
    box = [float(v) for v in sys.argv[2:6]]
    out_image = sys.argv[6] if len(sys.argv) > 6 else None

    hauteur = box[3] - box[1]
    score = score_mineur(image_path, box)

    if score is None:
        verdict = "INDETERMINE"
        score = 0.0
    elif hauteur < HAUTEUR_MIN_FIABLE:
        verdict = "INDETERMINE"
    elif score > SEUIL_MINEUR:
        verdict = "MINEUR"
    else:
        verdict = "adulte"

    if out_image:
        build_alert_image(image_path, box, out_image)

    print(f"{score:.3f} {verdict} {hauteur:.0f}")


if __name__ == '__main__':
    main()

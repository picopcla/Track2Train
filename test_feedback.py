import sys
import os
project_path = os.environ.get('TRACK2TRAIN_PATH', '/opt/app/Track2Train-staging')
sys.path.insert(0, project_path)

        points_fc = [p.get('hr') for p in points if p.get('hr') is not None and isinstance(p.get('hr'), (int, float))]
        if points_fc:
            activity['fc_moy'] = sum(points_fc) / len(points_fc)
            activity['fc_max'] = max(points_fc)
            activity['deriv_cardio'] = (points_fc[-1] / points_fc[0]) if points_fc[0] > 0 else 1.0
        else:
            activity['fc_moy'] = 0
            activity['fc_max'] = 0
            activity['deriv_cardio'] = 1.0
        activity['k_moy'] = 0
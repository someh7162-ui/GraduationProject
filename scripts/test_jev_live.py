"""Explicit smoke test using only synthetic questions and evidence, never the DB."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import jev


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Make three billed API requests with synthetic data')
    args = parser.parse_args()
    if not args.run:
        parser.error('Use --run to explicitly run the synthetic live test')
    if not os.getenv('TYPESAFE_API_KEY', '').strip():
        parser.error('TYPESAFE_API_KEY is not available in this process; reopen the terminal after setting it')
    os.environ['JEV_ENABLED'] = 'true'
    sources = [{'title': '虚构示例：星河校园图书馆通知',
                'snippet': '本通知纯属测试。星河校园图书馆开放时间为每天08:00至22:00。',
                'source_type': 'manual', 'verification_status': 'unverified'}]
    results = {
        'route': jev.route_question('我想了解国家奖学金申请资格，应该去哪个服务？'),
        'supported': jev.evidence_sufficient('示例中的图书馆每天几点开放？', sources),
        'unsupported': jev.evidence_sufficient('示例中的图书馆借书逾期每天罚款多少元？', sources),
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(result['source'] != 'jev' for result in results.values()):
        return 1
    return 0 if (results['route']['route'] == 'scholarship'
                 and results['supported']['status'] == 'sufficient'
                 and results['unsupported']['status'] == 'insufficient') else 2


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())

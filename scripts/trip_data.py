"""Portable, standard-library-only trip scaffold and structural checks.

This checks completeness, not truth, route feasibility or privacy compliance.
No network calls, credential reads, bookings or publication are performed.
"""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

PRACTICAL = ('preparation', 'immigration', 'connectivity', 'payments',
             'transport_cards', 'luggage', 'emergency', 'shopping', 'return')
STATUSES = {'confirmed', 'user_confirmed', 'estimate', 'unknown', 'paid'}


def dates(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first:
        raise ValueError('结束日期早于开始日期')
    return [(first + timedelta(days=i)).isoformat()
            for i in range((last - first).days + 1)]


def scaffold(destination, start, end, output_format):
    return {
        'meta': {'destination': destination, 'start': start, 'end': end,
                 'format': output_format, 'language': 'zh-CN', 'timezone': '',
                 'version': 'draft-1', 'privacy': 'public-generalized'},
        'preferences': {'travelers': None, 'budget': None, 'pace': '',
                        'interests': [], 'day_start': '', 'day_end': '',
                        'accessibility': ''},
        'sources': [], 'places': [], 'passes': [], 'budget': [],
        'days': [{'date': d, 'title': '', 'start': '', 'end': '',
                  'stops': [], 'legs': []} for d in dates(start, end)],
        'practical': {key: [] for key in PRACTICAL},
        'open_questions': []}


def validate(data):
    errors, warnings = [], []

    def need(obj, keys, where):
        if not isinstance(obj, dict):
            errors.append(f'{where}: 应为对象')
            return False
        for key in keys:
            if obj.get(key) is None or obj.get(key) == '':
                errors.append(f'{where}: 缺少 {key}')
        return True

    def rows(key):
        value = data.get(key)
        if not isinstance(value, list):
            errors.append(f'{key}: 应为列表')
            return []
        if not all(isinstance(item, dict) for item in value):
            errors.append(f'{key}: 列表项应为对象')
            return [item for item in value if isinstance(item, dict)]
        return value

    def index(items, name):
        found = set()
        for item in items:
            ident = item.get('id')
            if not isinstance(ident, str) or not ident:
                errors.append(f'{name}: 缺少有效字符串id')
            elif ident in found:
                errors.append(f'{name}: 重复id {ident}')
            else:
                found.add(ident)
        return found

    if not isinstance(data, dict):
        return ['顶层应为对象'], []
    meta = data.get('meta', {})
    if not need(meta, ('destination', 'start', 'end', 'format', 'timezone',
                       'version', 'privacy'), 'meta'):
        meta = {}
    if meta.get('format') not in {'web', 'pdf', 'both'}:
        errors.append('meta.format: 应为web/pdf/both')
    try:
        expected = dates(meta.get('start', ''), meta.get('end', ''))
    except (ValueError, TypeError):
        errors.append('meta: 日期无效或结束早于开始')
        expected = []
    sources, places = rows('sources'), rows('places')
    passes, budget, days = rows('passes'), rows('budget'), rows('days')
    source_ids = index(sources, 'sources')
    place_ids = index(places, 'places')
    pass_ids = index(passes, 'passes')
    index(budget, 'budget')

    def refs(item, where):
        ids = item.get('source_ids')
        if not isinstance(ids, list) or not ids:
            warnings.append(f'{where}: 无来源引用，需说明用户确认/估算依据')
        else:
            for ident in ids:
                if not isinstance(ident, str) or ident not in source_ids:
                    errors.append(f'{where}: 无效来源引用')

    def price(obj, where):
        if not need(obj, ('currency', 'basis', 'status'), where):
            return
        value = obj.get('amount')
        if obj.get('status') not in STATUSES:
            errors.append(f'{where}: 无效status')
        if value is None:
            warnings.append(f'{where}: 价格未知，不能当免费')
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            errors.append(f'{where}: amount应为非负数字或null')

    for source in sources:
        where = 'source ' + str(source.get('id', '?'))
        need(source, ('title', 'url', 'checked_on'), where)
        try:
            url = urlsplit(source.get('url', ''))
            if url.scheme not in {'http', 'https'} or not url.netloc:
                raise ValueError()
            date.fromisoformat(source.get('checked_on', ''))
        except (ValueError, TypeError, AttributeError):
            errors.append(f'{where}: URL或核验日期无效')
    for place in places:
        where = 'place ' + str(place.get('id', '?'))
        need(place, ('name',), where)
        booking = place.get('booking', {})
        need(booking, ('mode',), where + '.booking')
        if isinstance(booking, dict) and not booking.get('steps'):
            errors.append(f'{where}: 缺购票/入场步骤（免费点也须说明）')
        price(place.get('fee', {}), where + '.fee')
        refs(place, where)
    actual = [day.get('date') for day in days]
    if actual != expected:
        errors.append('days: 日期须连续、无重复且与meta范围一致')
    for day in days:
        where = str(day.get('date', '?'))
        need(day, ('title', 'start', 'end'), where)
        stops, legs = day.get('stops', []), day.get('legs', [])
        if not isinstance(stops, list) or not isinstance(legs, list):
            errors.append(f'{where}: stops/legs应为列表')
            continue
        if not stops:
            errors.append(f'{where}: 无行程点')
        stop_ids = []
        for stop in stops:
            if not need(stop, ('place_id',), where + '.stop'):
                continue
            ident = stop.get('place_id')
            if not isinstance(ident, str) or ident not in place_ids:
                errors.append(f'{where}: 无效景点引用')
            stop_ids.append(ident)
        if len(legs) != max(0, len(stops) - 1):
            errors.append(f'{where}: 相邻行程点须有对应交通段')
        for i, leg in enumerate(legs):
            label = f'{where}.leg{i + 1}'
            if not need(leg, ('from', 'to', 'mode', 'route', 'duration_min', 'boarding'), label):
                continue
            duration = leg.get('duration_min')
            if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
                errors.append(f'{label}: duration_min须为正数门到门用时')
            if i + 1 < len(stop_ids) and (leg.get('from'), leg.get('to')) != tuple(stop_ids[i:i + 2]):
                errors.append(f'{label}: 与相邻行程点不连续')
            price(leg.get('fare', {}), label + '.fare')
            refs(leg, label)
    for entry in budget:
        label = 'budget ' + str(entry.get('id', '?'))
        need(entry, ('label', 'quantity'), label)
        price(entry, label)
        included = entry.get('included_in')
        if included and (not isinstance(included, str) or included not in pass_ids):
            errors.append(f'{label}: included_in未引用已有票券')
        if included:
            warnings.append(f'{label}: 套餐覆盖明细不得重复计费')
    practical = data.get('practical', {})
    if not isinstance(practical, dict):
        errors.append('practical: 应为对象')
        practical = {}
    for key in PRACTICAL:
        if not isinstance(practical.get(key), list) or not practical[key]:
            errors.append(f'practical.{key}: 缺少可执行指南')
    if not sources:
        errors.append('sources: 缺少核验来源')
    if not budget:
        warnings.append('budget: 无预算，需解释是否主动省略')
    if data.get('open_questions'):
        warnings.append('有待确认事项，交付时必须披露')
    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    for flag in ('destination', 'start', 'end', 'output'):
        init.add_argument('--' + flag, required=True)
    init.add_argument('--format', choices=('web', 'pdf', 'both'), required=True)
    check = sub.add_parser('validate')
    check.add_argument('file')
    args = parser.parse_args()
    try:
        if args.command == 'init':
            result = scaffold(args.destination, args.start, args.end, args.format)
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation protects a user's existing plan from overwrite.
            with target.open('x', encoding='utf-8') as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
            print('已创建待填骨架；尚未研究，不是成品。')
            return 0
        with Path(args.file).open(encoding='utf-8-sig') as stream:
            data = json.load(stream)
        errors, warnings = validate(data)
        # Only field identifiers are reported; never echo raw records or URLs.
        for message in errors:
            print('错误: ' + message)
        for message in warnings:
            print('提醒: ' + message)
        print(f'结构检查: {len(errors)}项错误，{len(warnings)}项提醒。事实/隐私/视觉仍需人工验收。')
        return 1 if errors else 0
    except FileExistsError:
        print('目标文件已存在，未覆盖。', file=sys.stderr)
    except (OSError, ValueError, TypeError):
        print('无法处理输入：请检查路径、JSON结构和日期。未输出原始数据。', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())

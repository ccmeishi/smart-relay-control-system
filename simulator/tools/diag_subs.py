"""通过 EMQX Dashboard API 查询所有 MQTT 订阅, 找 JetLinks 的 topic filter"""
import json
import base64
import urllib.request

out_lines = []
try:
    auth = base64.b64encode(b'admin:public').decode()
    url = 'http://172.16.4.211:18083/api/v5/subscriptions?limit=300'
    req = urllib.request.Request(url, headers={'Authorization': 'Basic ' + auth})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    items = data.get('data', [])
    out_lines.append(f'订阅总数: {len(items)}')
    out_lines.append('')
    for it in items:
        clientid = it.get('clientid', '?')
        topic = it.get('topic', '?')
        out_lines.append(f'  client={clientid}  topic={topic}')
except Exception as e:
    out_lines.append(f'API 查询失败: {type(e).__name__}: {e}')

with open('diag_subs.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out_lines))
print('done', len(out_lines))

import time
import json
import requests
import geojson
from transCoordinateSystem import gcj02_to_wgs84


def get_envelope(key, keywords):  # 获取最小外包矩形
    url = 'http://restapi.amap.com/v3/config/district?' + 'keywords=' + keywords + '&key=' + key + '&subdistrict=0' + '&extensions=all'
    res = requests.get(url)
    json_obj = json.loads(res.text)
    if res.status_code != 200:
        raise Exception
    if int(json_obj["infocode"]) != 10000:
        raise Exception
    if 'polyline' not in json_obj["districts"][0]:
        raise Exception
    polylines = json_obj["districts"][0]['polyline'].split('|')
    n_part = len(polylines)
    part = polylines[0].split(';')
    lon0, lat0 = part[1].split(',')
    tmp = [float(lon0), float(lat0), float(lon0), float(lat0)]
    tmp = caculate_envelope(tmp, part)
    for i in range(1, n_part):  # 其他部分
        part = polylines[i].split(';')
        tmp = caculate_envelope(tmp, part)
    return tmp


def caculate_envelope(tmp, cords):
    minlon, maxlat, maxlon, minlat = tmp
    for cord in cords:
        lon, lat = cord.split(',')
        if float(lat) > maxlat:
            maxlat = float(lat)
        elif float(lat) < minlat:
            minlat = float(lat)
        if float(lon) > maxlon:
            maxlon = float(lon)
        elif float(lon) < minlon:
            minlon = float(lon)
    return [minlon, maxlat, maxlon, minlat]


def split_envelope(envelope, step):
    minlon, maxlat, maxlon, minlat = envelope
    nlon = int((maxlon - minlon + 0.0001) // step + 1)
    nlat = int((maxlat - minlat + 0.0001) // step + 1)
    rect_list = []
    for i in range(nlon):
        for j in range(nlat):
            rect_list.append([round(minlon + step * i, 4), round(minlat + step * j + step, 4),
                              round(minlon + step * i + step, 4), round(minlat + step * j, 4)])
    return rect_list


def split_rect(rect):
    # 四等分矩形
    minlon, maxlat, maxlon, minlat = rect
    midlon = (maxlon + minlon) / 2
    midlat = (maxlat + minlat) / 2
    sw = [minlon, midlat, midlon, minlat]
    se = [midlon, midlat, maxlon, minlat]
    nw = [minlon, maxlat, midlon, midlat]
    ne = [midlon, maxlat, maxlon, midlat]
    return [sw, se, nw, ne]


def to_urlstring(rect):
    return str(rect[0]) + ',' + str(rect[1]) + ';' + str(rect[2]) + ',' + str(rect[3])  # 坐标字符串


def get_traffic_info(rect, key):
    traffic_json = []
    while True:
        # 获取给定矩形的路况
        url = 'https://restapi.amap.com/v3/traffic/status/rectangle?' + 'rectangle=' + to_urlstring(rect) \
              + '&key=' + key + '&level=6&extensions=all'
        res = requests.get(url)
        if res.status_code != 200:
            print('Network Error! Reloading...')
            continue
        traffic_json = json.loads(res.text)
        infocode = int(traffic_json["infocode"])
        if infocode == 10000:  # 获取成功
            break
        else:
            raise Exception('API Error')
    return get_road_info(traffic_json)


def get_road_info(traffic_json):
    if len(traffic_json) == 0:
        return []
    roads = traffic_json['trafficinfo']['roads']
    roads_json = []
    for road in roads:
        lonlats = road['polyline'].split(';')
        polyline = []
        for lonlat in lonlats:
            lon, lat = lonlat.split(',')
            point = gcj02_to_wgs84(float(lon), float(lat))
            polyline.append(point)
        geom = geojson.LineString(polyline)
        speed = ''
        if 'speed' in road:  # 部分路段无该属性
            speed = road['speed']
        properties = {'name': road['name'], 'status': road['status'],
                      'direction': road['direction'],
                      'angle': road['angle'],
                      'speed': speed}
        road_json = {
            "type": "Feature",
            "properties": properties,
            "geometry": geom}
        roads_json.append(road_json)
    return roads_json


def write_to_geojson(roads_json, filename='traffic'):
    res_geojson = {
        "type": "FeatureCollection",
        "features": roads_json}
    res_file = open(filename + ".geojson", 'w')
    res_file.write(geojson.dumps(res_geojson) + '\n')
    res_file.close()


if __name__ == '__main__':
    keywords = '110108'  # 海淀
    key = '4262b19287a948cbcce10fce29863d1b'
    envelope = get_envelope(key, keywords)  # 获取范围
    rects = split_envelope(envelope, 0.05)  # 矩形对角线不能超过10公里
    n = len(rects)
    roadlist = []
    print("Started. Pleas wait...")
    start_time = time.time()
    for i in range(0, n):
        roadlist.extend(get_traffic_info(rects[i], key))
        print("Total: %d. Finished: %d" % (n, i + 1))
    write_to_geojson(roadlist, keywords + '_Road')
    end_time = time.time()
    print("Completed. Time_consuming: %.2f s" % (end_time - start_time))

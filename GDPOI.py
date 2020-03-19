import time
import json
import requests
import os
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
    return str(rect[0]) + ',' + str(rect[1]) + '|' + str(rect[2]) + ',' + str(rect[3])  # 坐标字符串


def get_poi_json(rect, page, key):
    # 参考官方文档 https://lbs.amap.com/api/webservice/guide/api/search#polygon
    poi_json=[]
    while True:
        # 获取指定矩形指定页的POI
        url = 'https://restapi.amap.com/v3/place/polygon?' + 'polygon=' + to_urlstring(rect) + '&offset=20' + '&page=' \
              + str(page) + "&types=010000|020000|030000|040000|050000|060000|070000|080000|090000|100000|110000|" \
                            "120000|130000|140000|150000|160000|170000|180000|190000|200000|220000|970000|990000" \
              + "&key=" + key
        res = requests.get(url)
        if res.status_code != 200:
            print('Network Error! Reloading...')
            continue
        poi_json = json.loads(res.text)
        infocode = int(poi_json["infocode"])
        if infocode == 10000:  # 获取成功
            break
        elif infocode >= 20000:
            print(url)
            print("Error:%d, For more information: https://lbs.amap.com/api/webservice/guide/tools/info/" % infocode)
            break
        else:
            print(url)
            # 如有多个key可在此处替换
            raise Exception('No valid API key')
    return poi_json


def get_poi(rect, key):
    pois_json = get_poi_json(rect, 1, key)
    if 'count' not in pois_json:
        return []
    else:
        poi_count = int(pois_json['count'])
    if poi_count == 0:
        return []
    if poi_count > 850:
        srects = split_rect(rect)  # 单次返回的上限在900左右，为避免遗漏需重新分块
        poi = []
        for srect in srects:
            poi.extend(get_poi(srect, key))
        return poi
    else:
        poi = pois_json['pois']  # 第1页
        maxPage = poi_count // 20 + 1  # 页数
        for i in range(2, maxPage + 1):  # 第2页到最后
            poi.extend(get_poi_json(rect, i, key))
        return poi


def write_to_geojson(poilist, filename='poi_geo'):
    poi_json = []
    n = len(poilist)
    for i in range(n):
        if 'location' not in poilist[i]:
            continue
        location = poilist[i]['location']
        lon, lat = str(location).split(",")
        result = gcj02_to_wgs84(float(lon), float(lat))  # 坐标纠正
        geom = geojson.Point((result[0], result[1]))
        properties = {'id': poilist[i]['id'], 'name': poilist[i]['name'], 'address': poilist[i]['address'],
                      'adname': poilist[i]['adname'],
                      'typecode': poilist[i]['typecode'],
                      'type': poilist[i]['type']}
        temp = {
            "type": "Feature",
            "properties": properties,
            "geometry": geom}
        poi_json.append(temp)
    pois_json = {
        "type": "FeatureCollection",
        "features": poi_json}
    res_file = open(filename + ".geojson", 'w')
    res_file.write(geojson.dumps(pois_json) + '\n')
    res_file.close()


if __name__ == '__main__':
    keywords = '110108'  # 海淀
    key = '4262b19287a948cbcce10fce29863d1b'
    envelope = get_envelope(key, keywords)  # 获取范围
    rects = split_envelope(envelope, 0.01)  # 根据需要分块
    n = len(rects)
    poilist = []
    print("Started. Pleas wait...")
    start_time = time.time()
    for i in range(0, n):
        poilist.extend(get_poi(rects[i], key))
        print("Total: %d. Finished: %d" % (n, i + 1))
    write_to_geojson(poilist, keywords + '_POI')
    end_time = time.time()
    print("Completed. Time_consuming: %.2f s" % (end_time - start_time))

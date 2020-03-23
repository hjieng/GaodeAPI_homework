import time
import json
import requests
import geojson
from transCoordinateSystem import gcj02_to_wgs84


# 行政区域边界获取,参考官方文档 https://lbs.amap.com/api/webservice/guide/api/district 目前不支持返回乡镇/街道级别的边界值

def get_resjson(key, keywords, subdistrict, extensions):
    parameter = {"key": key, "keywords": keywords, "subdistrict": subdistrict, "extensions": extensions}
    url = "http://restapi.amap.com/v3/config/district"
    res = requests.get(url, params=parameter)
    resjson = json.loads(res.text)
    if res.status_code != 200:
        raise Exception
    if int(resjson["infocode"]) != 10000:
        raise Exception
    return resjson


def get_border(key, keywords):
    resjson = get_resjson(key, keywords, 0, 'all')
    district = resjson["districts"][0]
    if 'polyline' not in district:
        return {}
    cords = district['polyline'].split('|')
    polylines = []
    for cord in cords:
        lonlats = cord.split(';')
        polyline = []
        for lonlat in lonlats:
            lon, lat = lonlat.split(',')
            point = gcj02_to_wgs84(float(lon), float(lat))
            polyline.append(point)
        polylines.append(polyline)
    geom = geojson.MultiLineString(polylines)  # 多边形的拓扑关系不明，故使用线
    properties = {'citycode': district['citycode'],
                  'adcode': district['adcode'],
                  'name': district['name'],
                  'level': district['level']}
    border = {"type": "Feature",
              "properties": properties,
              "geometry": geom}
    return border


def find_exausted(district):
    # 获取区域和子区域的adcode
    adcodes = [district['adcode']]
    subdistricts = district["districts"]
    if len(subdistricts) == 0:
        return adcodes
    for subdistrict in subdistricts:
        subadcodes = find_exausted(subdistrict)
        adcodes.extend(subadcodes)
    return adcodes


def get_adcodes(key, keywords):
    resjson = get_resjson(key, keywords, 3, 'base')
    district = resjson["districts"][0]
    adcodes = find_exausted(district)
    return adcodes


def get_borders(key, adcodes):
    borderlist = []
    for adcode in adcodes:
        border = get_border(key, adcode)
        if len(border) > 0:
            borderlist.append(border)
    return borderlist


def write_to_geojson(borderlist, filename='border'):
    res_geojson = {
        "type": "FeatureCollection",
        "features": borderlist}
    res_file = open(filename + ".geojson", 'w')
    res_file.write(geojson.dumps(res_geojson) + '\n')
    res_file.close()


if __name__ == '__main__':
    key = '4262b19287a948cbcce10fce29863d1b'
    # 由于称呼的差异和二义性, keywords建议使用adcode, 参考 https://lbs.amap.com/api/webservice/download
    # keywords = '100000'  # 中国  #获取全国最好分块
    keywords = '110000'  # 北京
    print("Started. Pleas wait...")
    start_time = time.time()
    adcodes = get_adcodes(key, keywords)  # 获取所有adcode
    unique_adcodes = sorted(set(adcodes), key=adcodes.index)  # 去重
    boderlist = get_borders(key, unique_adcodes)  # 获取边界
    write_to_geojson(boderlist, keywords)  # 写入文件
    end_time = time.time()
    print("Completed. Time_consuming: %.2f s" % (end_time - start_time))

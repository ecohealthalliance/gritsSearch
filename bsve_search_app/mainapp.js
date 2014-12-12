/* Copyright 2014 Kitware Inc.
 *
 * Licensed under the Apache License, Version 2.0 ( the "License" );
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

var app = angular.module(
    'Girder App', ['harbingerComponents', 'ngCookies']);
app.controller('AppController', function($scope, $http, $cookies) {
    var geo_map = null, geo_layer, geo_feature, drawWait = false,
        drawQueued = false, lastPicked = null, highlightedList = [];

    function triggerDraw() {
        if (!drawWait) {
            geo_map.draw();
            drawWait = true;
            window.setTimeout(function () {
                drawWait = false;
            }, 100);
            return;
        }
        if (!drawQueued) {
            drawQueued = true;
            window.setTimeout(function () {
                geo_map.draw();
                drawQueued = false;
            }, 100);
        }
    }

    function showMap(data) {
        if (!geo_map) {
            geo_map = geo.map({
                node: '#grits-map',
                zoom: 1
            });
            geo_map.createLayer(
                'osm',
                {
                    baseUrl: 'http://otile1.mqcdn.com/tiles/1.0.0/map/'
                }
            );
            geo_layer = geo_map.createLayer('feature');
            geo_feature = geo_layer.createFeature('point',
                                                  {selectionAPI:true});
        }
        geo_feature.data(data)
            .style({
                fillColor: function (d) {
                    return d.picked ? (d.highlighted ? '#80FFFF' : 'aqua') :
                           d.highlighted ? 'yellow' : 'steelblue';
                },
                fillOpacity: function (d) {
                    return d.highlighted ? 0.9 : 0.65;
                },
                strokeColor: 'black',
                strokeWidth: 1,
                radius: function (d) {
                    var count = d.ids.length;
                    var rad = 7 - Math.log10(data.length);
                    rad = rad < 4 ? 4 : rad;
                    rad += Math.log10(count)*2;
                    return rad > 15 ? 15 : rad;
                },
            })
            .position(function (d) {
                return {
                    x: d.coordinates[0],
                    y: d.coordinates[1]
                };
            })
            .geoOff(geo.event.feature.mouseclick)
            .geoOn(geo.event.feature.mouseclick, function (evt) {
                if (evt.zIndex !== 0) {
                    // Only handle the top element clicked
                    return;
                }
                var elemId = getDomId(evt.data);
                $('.picked').removeClass('picked');
                var elems = $(elemId).addClass('picked');
                scrollToCenter(elems, 10);
                $scope.unpick();
                lastPicked = evt.data;
                evt.data.picked = true;
                $scope.selectedDescription = evt.data.place.place_name;
                if (!evt.data.place.place_name) {
                    $scope.selectedDescription = evt.data.coordinates[0] +
                        ', '  + evt.data.coordinates[1];
                }
                $scope.selectedTitle = evt.data.place.place_name;
                $scope.selectedCount = evt.data.ids.length;
                $scope.selectedLocation = true;
                $scope.$apply();
                reorderData();
                this.modified();
                triggerDraw();
            })
            .geoOff(geo.event.feature.mouseover)
            .geoOn(geo.event.feature.mouseover, function (evt) {
                highlightPoint('add', evt.data);
                var elemId = getDomId(evt.data);
                $(elemId).addClass('highlighted');
            })
            .geoOff(geo.event.feature.mouseout)
            .geoOn(geo.event.feature.mouseout, function (evt) {
                highlightPoint('clear', evt.data);
                var elemId = getDomId(evt.data);
                $(elemId).removeClass('highlighted');
            });
        geo_map.draw();
    }

    function scrollToCenter(elem, minOffset) {
        /* Vertically scroll the jquery element(s) so that elements are
         * centered within the visible area of the parent, if possible.  If not
         * possible, scroll so the topmost element is near the top of the
         * visible area.
         *
         * :param elem: a jquery element set.
         * :param minOffset: if present, try to always leave this many pixels
         *     between the top of the visible area and the elements.
         */
        if (!elem.length) {
            return;
        }
        var position = elem.position();
        var height = elem.outerHeight(true);
        elem.each(function (idx, el) {
            el = $(el);
            var pos = el.position();
            if (pos.top < position.top) {
                height += position.top - pos.top;
                position.top = pos.top;
            }
            h = el.outerHeight(true);
            if (pos.top + h > position.top + height) {
                height = pos.top + h - position.top;
            }
        });
        var scrollElem = elem.parents().filter(function() {
            var parent = $( this );
            return (/(auto|scroll)/).test(parent.css('overflow') +
                                          parent.css('overflow-y'));
        }).eq(0);;
        var curScroll = scrollElem.scrollTop();
        var view = scrollElem.height();
        var offset = (view - height) / 2;
        if (minOffset && offset < minOffset) {
            offset = minOffset;
        }
        if (offset > 0) {
            position.top -= offset;
        }
        scrollElem.scrollTop(curScroll + position.top);
    }

    function highlightPoint(action, point) {
        /* Add, remove, or remove all points from the points that might be
         * highlighted.  Make sure only the topmost point in the candidate
         * list is actually highlighted.
         *
         * :param action: 'add' to add a point to the list, 'clear' to
         *     remove a point from the list, or 'clearall' to remove all
         *     points from the list.
         * :param point: the point to add or clear.
         */
        var update = false, recheck = false, tooltip;
        switch (action) {
            case 'add':
                var idx = highlightedList.indexOf(point);
                if (idx >= 0) {
                    return;
                }
                highlightedList.push(point);
                recheck = true;
                break;
            case 'clear':
                var idx = highlightedList.indexOf(point);
                if (idx >= 0) {
                    if (point.highlighted) {
                       delete point.highlighted;
                       update = true;
                    }
                    highlightedList.splice(idx, 1);
                    recheck = true;
                }
                break;
            case 'clearall':
                for (var i = 0; i < highlightedList.length; i += 1) {
                    if (highlightedList[i].highlighted) {
                        delete highlightedList[i].highlighted;
                        update = true;
                    }
                }
                highlightedList = [];
                break;
        }
        if (recheck) {
            var topmost = -1, toppos = -1;
            for (var i=0; i < highlightedList.length; i += 1) {
                if (highlightedList[i].position > toppos) {
                    toppos = highlightedList[i].position;
                    topmost = i;
                }
            }
            for (var i=0; i < highlightedList.length; i += 1) {
                if (i == topmost && !highlightedList[i].highlighted) {
                    highlightedList[i].highlighted = true;
                    tooltip = highlightedList[i];
                    update = true;
                } else if (i != topmost && highlightedList[i].highlighted) {
                    delete highlightedList[i].highlighted;
                    update = true;
                }
            }
        }
        if (update) {
            geo_feature.modified();
            triggerDraw();
            if (!tooltip) {
                if ($scope.mapTooltip) {
                    $scope.mapTooltip = null;
                    $scope.$apply();
                }
            } else {
                var tt = {style: '', alerts: []};
                var pos = geo_map.gcsToDisplay({
                    x: tooltip.coordinates[0], y: tooltip.coordinates[1]});
                var mapW = $('#grits-map').width();
                var mapH = $('#grits-map').height();
                if (pos.x > mapW/2) {
                    tt.style += 'right: '+(mapW-pos.x+10)+'px';
                } else {
                    tt.style += 'left: '+(pos.x+10)+'px';
                }
                if (pos.y > mapH/2) {
                    tt.style += '; bottom: '+(mapH-pos.y+10)+'px';
                } else {
                    tt.style += '; top: '+(pos.y+10)+'px';
                }
                tt.title = tooltip.place.place_name || (
                    tooltip.coordinates[0] + ', '  + tooltip.coordinates[1]);
                var maxlist = 3;
                for (var i = 0; i < tooltip.ids.length && i < maxlist; i +=1) {
                    var elem = $('#alert-' + tooltip.ids[i]);
                    var date = $('.result-date', elem).text();
                    var desc = $('.result-description', elem).text();
                    tt.alerts.push({date: date.substr(0, 10),
                                    description: desc,
                                    id: tooltip.ids[i]});
                }
                if (tooltip.ids.length > maxlist) {
                    tt.alerts.push({description: 'and ' +
                        (tooltip.ids.length - maxlist) + ' more ...'});
                }
                $scope.mapTooltip = tt;
                $scope.$apply();
            }
        }
    }

    function getDomId(pointRecord) {
        return '#alert-'+pointRecord.ids.join(',#alert-');
    }

    function reorderData() {
        // reorders the data in point feature class
        var data = geo_feature.data();
        var newData = [];
        data.forEach(function (d) {
            if (!d.picked) {
                d.position = newData.length;
                newData.push(d);
            }
        });
        data.forEach(function (d) {
            if (d.picked) {
                d.position = newData.length;
                newData.push(d);
            }
        });
        geo_feature.data(newData);
    }

    $scope.ready = false;

    $scope.highlightAlert = function (result) {
        highlightPoint('clearall');
        $('.highlighted').removeClass('highlighted');
        for (var n=0; n<result.points.length; n++) {
            result.points[n].highlighted = true;
        }
        geo_feature.modified();
        triggerDraw();
    };

    $scope.unhighlightAlert = function (result) {
        highlightPoint('clearall');
        $('.highlighted').removeClass('highlighted');
        for (var n=0; n<result.points.length; n++) {
            delete result.points[n].highlighted;
        }
        geo_feature.modified();
        triggerDraw();
    };

    $scope.unpick = function () {
        if (lastPicked) {
            if (lastPicked.points) {
                for (var n=0; n<lastPicked.points.length; n++) {
                    delete lastPicked.points[n].picked;
                }
            } else if (lastPicked.picked) {
                delete lastPicked.picked;
            }
        }
        lastPicked = null;
    }

    $scope.transitionTo = function (result) {
        var elemId = '#alert-' + result.properties.id;
        $('.picked').removeClass('picked');
        $(elemId).addClass('picked');
        $scope.unpick();
        for (var n=0; n<result.points.length; n++) {
            result.points[n].picked = true;
        }
        $scope.selectedDescription = 'Alert '+result.properties.id;
        $scope.selectedTitle = result.properties.date + ': ' +
                               result.properties.summary;
        $scope.selectedCount = result.points.length;
        $scope.selectedLocation = false;
        lastPicked = result;
        reorderData();
        geo_feature.modified();
        var center = result.points[0].coordinates;
        var zoom = 5;
        if (result.points.length > 1) {
            /* If our map wrapped east to west, this would be wrong. */
            var extents = [center[0], center[1], center[0], center[1]];
            for (var i=1; i<result.points.length; i++) {
                var coor = result.points[i].coordinates;
                if (coor[0]<extents[0]) { extents[0] = coor[0]; }
                if (coor[1]<extents[1]) { extents[1] = coor[1]; }
                if (coor[0]>extents[2]) { extents[2] = coor[0]; }
                if (coor[1]>extents[3]) { extents[3] = coor[1]; }
            }
            center = [(extents[0]+extents[2])*0.5,
                      (extents[1]+extents[3])*0.5];
            zoom = geo_map.zoom();
            var upperLeft = geo_map.displayToGcs({x: 0, y: 0});
            var lowerRight = geo_map.displayToGcs({
                x: $('#grits-map').width(), y: $('#grits-map').height()});
            var fillX = (extents[2]-extents[0])/(lowerRight.x-upperLeft.x);
            var fillY = (extents[3]-extents[1])/(upperLeft.y-lowerRight.y);
            var fill = fillX > fillY ? fillX : fillY;
            while (fill > 0.9) {
                zoom -= 1;
                fill /= 2;
            }
            while (fill < 0.45) {
                zoom += 1;
                fill *= 2;
            }
            if (zoom > 6) {
                zoom = 6;
            }
        }
        geo_map.transition({
            center: {
                x: center[0],
                y: center[1]
            },
            zoom: zoom,
            interp: d3.interpolateZoom,
            duration: 1000
        });
    };

    $scope.changeFilter = function () {
        /* I don't know why angular doesn't change this on its own */
        $scope.selectedFilter = !$scope.selectedFilter;
    }

    $scope.url = 'http://localhost:8081';
    if ($cookies.girderUrl) {
        $scope.url = $cookies.girderUrl;
    }
    $scope.loginParams = [{
            key: 'url',
            value: $scope.url,
            label: 'Girder URL',
            placeholder: 'URL to girder server',
            title: 'Do not include a trailing slash.'
        },{ key: 'username', label: 'User Name'
        },{ key: 'password', label: 'Password', style: 'password'
    }];
    $scope.params = [{
            key: 'start',
            label: 'Start date',
            placeholder: 'Start date (inclusive)',
            title: 'Date format is YYYY-MM-DD.'
        },{
            key: 'end',
            label: 'End date',
            placeholder: 'End date (exclusive)',
            title: 'Date format is YYYY-MM-DD.'
        },{ key: 'country', label: 'Country'
        },{ key: 'disease', label: 'Disease'
        },{ key: 'species', label: 'Species'
        },{ key: 'description', label: 'Description'
        },{ key: 'diagnosis', label: 'Diagnosis'
        },{ key: 'id', label: 'Incident ID'
        },{
            key: 'limit',
            label: 'Limit',
            placeholder: '(default is 50, 0 for all)'
        },{ key: 'offset', label: 'Offset'
    }];
    if (!$scope.userToken && $cookies.girderToken) {
        $scope.userToken = $cookies.girderToken;
    }
    for (var i = 0; i < $scope.params.length; i += 1) {
        var param = $scope.params[i];
        param.style = param.style || 'text';
        param.placeholder = param.placeholder || '';
    }

    $scope.onReady = function() {
        // API has a connection with BSVE workbench
        $scope.ready = true;
    };

    $scope.login = function() {
        var url, username, password;
        for (var i = 0; i < $scope.loginParams.length; i += 1) {
            var param = $scope.loginParams[i];
            switch (param.key) {
                case 'url': url = param.value; break;
                case 'username': username = param.value; break;
                case 'password': password = param.value; break;
            }
        }
        if (username && password) {
            $scope.url = url;
            var auth = 'Basic ' + btoa(username + ':' + password);
            $http.defaults.headers.common.Authorization = auth;
            $http.get(url + '/api/v1/user/authentication').success(
                    function (data) {
                $scope.userToken = data.authToken.token;
                $cookies.girderToken = $scope.userToken;
                $cookies.girderUrl = url;
                $scope.loginError = null;
                $scope.resultsPending = null;
            }).error(function (error) {
                $scope.loginError = error.message;
            });
        }
    };

    $scope.logout = function() {
        $scope.results = null;
        $scope.resultsError = null;
        $scope.userToken = null;
        $cookies.girderToken = '';
        $scope.resultsPending = null;
        $scope.loginError = null;
        $scope.selectedDescription = null;
        $scope.selectedLocation = null;
    };

    $scope.collectPoint = function (points, id, coordinates, place) {
        for (var i=0; i<points.length; i++) {
            if (points[i].coordinates[0] == coordinates[0] &&
                    points[i].coordinates[1] == coordinates[1]) {
                points[i]['ids'].push(id);
                return points[i];
            }
        }
        var point = {
            ids: [id],
            coordinates: coordinates,
            position: points.length,
            place: place
        };
        points.push(point);
        return point;
    };

    $scope.search = function() {
        var params = {}, url, username, password;
        for (var i = 0; i < $scope.params.length; i += 1) {
            var param = $scope.params[i];
            if (param.value !== null && param.value !== undefined &&
                    param.value.length) {
                params[param.key] = param.value;
            }
        }
        params.token = $scope.userToken;
        params.geoJSON = 1;
        $scope.results = null;
        $scope.resultsError = null;
        $scope.resultsPending = true;
        $scope.getData(params, params.limit, 0);
    };

    /* Fetch data in pages so as not to overtax the memory of the girder
     * server. */
    $scope.getData = function (params, limit, data, gjson) {
        if (limit !== undefined) {
            limit = parseInt(limit);
        }
        var pageSize = 5000;
        var needMore = (!data);
        if (gjson) {
            var newdata = ((gjson || {}).features || []);
            needMore = (newdata.length == pageSize);
            if (data) {
                for (var i=0; i < newdata.length; i++) {
                    data.push(newdata[i]);
                }
            } else {
                data = newdata;
            }
            if (limit && data.length >= limit) {
                needMore = false;
            }
            params.offset = (params.offset || 0) + pageSize;
        }
        if (needMore) {
            if (limit !== undefined && (!limit || limit >= pageSize)) {
                params.limit = pageSize;
                if (limit && data && limit - data.length < pageSize) {
                    params.limit = limit - data.length;
                }
            }
            $http.get($scope.url + '/api/v1/resource/grits?' + $.param(params)
                ).success(function (gjson) {
                    $scope.getData(params, limit, data, gjson);
            }).error(function (error) {
                $scope.resultsPending = null;
                $scope.results = null;
                $scope.resultsError = 'Failed to get any results';
            });
            return;
        }
        var points = [];
        /* Split alerts with multiple events into multiple items */
        for (var i=0; i < data.length; i++) {
            var item = data[i];
            item.properties.link = 'http://www.healthmap.org/ln.php?' +
                item.properties.id.substr(0, item.properties.id.length-4);
            item.points = [];
            if ($.isArray(item.geometry.coordinates[0])) {
                item.numPoints = item.geometry.coordinates.length;
                for (var n=0; n < item.numPoints; n++) {
                    item.points.push($scope.collectPoint(
                        points, item.properties.id,
                        item.geometry.coordinates[n],
                        item.properties.places[n]));
                }
            } else {
                item.numPoints = 1;
                item.points.push($scope.collectPoint(
                    points, item.properties.id, item.geometry.coordinates,
                    item.properties.places[0]));
            }
        }
        $scope.results = data;
        $scope.resultsPending = null;
        $scope.resultsError = null;
        $scope.selectedDescription = null;
        $scope.selectedLocation = null;
        lastPicked = null;
        highlightedList = [];
        showMap(points);
    };

    API.init($http, $scope.onReady);
});


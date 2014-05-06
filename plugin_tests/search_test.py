#!/usr/bin/env python
# -*- coding: utf-8 -*-

###############################################################################
#  Copyright 2013 Kitware Inc.
#
#  Licensed under the Apache License, Version 2.0 ( the "License" );
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import json
from datetime import datetime

import bson.json_util
from bson.objectid import ObjectId

from tests import base
from girder.constants import AccessType

admin = {
    'email': 'grits@email.com',
    'login': 'grits',
    'firstName': 'grits',
    'lastName': 'grits',
    'password': 'gritspassword',
    'admin': True
}

privUser = {
    'email': 'gritsPriv@email.com',
    'login': 'gritsPriv',
    'firstName': 'First',
    'lastName': 'Last',
    'password': 'goodpassword',
    'admin': False
}

gritsUser = {
    'email': 'gritsUser@email.com',
    'login': 'gritsUser',
    'firstName': 'First',
    'lastName': 'Last',
    'password': 'goodpassword',
    'admin': False
}

normalUser = {
    'email': 'normalUser@email.com',
    'login': 'normalUser',
    'firstName': 'First',
    'lastName': 'Last',
    'password': 'goodpassword',
    'admin': False
}

incidents = [
    {
        "description": "description 1",
        "name": "1000",
        "meta": {
            "country": "country1",
            "feed": "feed 1",
            "rating": 1,
            "description": "long description 1",
            "disease": "disease 1",
            "longitude": 0,
            "latitude": 0,
            "link": "www.kitware.com",
            "date": datetime(2012, 1, 1)
        },
        "private": {
            "privatekey1": "private value 1",
            "privatekey2": 0
        }
    },
    {
        "description": "description 2",
        "name": "1001",
        "meta": {
            "country": "country2",
            "feed": "feed 1",
            "rating": 2,
            "description": "long description 2",
            "disease": "disease 2",
            "longitude": 5,
            "latitude": 5,
            "link": "www.google.com",
            "date": datetime(2012, 2, 1)
        },
        "private": {
            "privatekey1": "something",
            "privatekey3": "private value 2",
            "privatekey2": 1
        }
    },
    {
        "description": "description 3",
        "name": "1002",
        "meta": {
            "country": "country2",
            "feed": "feed 2",
            "rating": 3,
            "description": "long description 3",
            "disease": "disease 1",
            "longitude": 10,
            "latitude": 15,
            "link": "www.github.com",
            "date": datetime(2012, 2, 5)
        },
        "private": {
            "privatekey1": "private value 1",
            "privatekey2": 11
        }
    }
]


def setUpModule():
    base.enabledPlugins.append('gritsSearch')

    base.startServer()


def tearDownModule():
    base.stopServer()


class GritsSearchTestCase(base.TestCase):

    def setUpGroups(self):
        self.admin = self.model('user').createUser(**admin)
        self.normalUser = self.model('user').createUser(**normalUser)

    def testGritsPermissions(self):

        def requests(user, status):
            resp = self.request(
                path='/resource/grits',
                method='GET',
                user=user
            )
            self.assertStatus(resp, status[0])

            resp = self.request(
                path='/resource/grits/groupId',
                method='GET',
                user=user
            )
            self.assertStatus(resp, status[0])

            resp = self.request(
                path='/resource/grits/folderId',
                method='GET',
                user=user
            )
            self.assertStatus(resp, status[0])

            resp = self.request(
                path='/resource/grits/collectionId',
                method='GET',
                user=user
            )
            self.assertStatus(resp, status[0])

            resp = self.request(
                path='/resource/grits/privilegedId',
                method='GET',
                user=user
            )
            self.assertStatus(resp, status[1])

        self.setUpGroups()

        # test admin permissions
        requests(self.admin, (200, 200))

        # test non grits user permissions
        requests(self.normalUser, (403, 403))

        # test normal grits user permissions
        gritsGroup = self.model('group').find({'name': 'GRITS'})[0]
        user = self.model('user').createUser(**gritsUser)
        self.model('group').addUser(gritsGroup, user)

        requests(user, (200, 403))

        # test privilaged grits user permissions
        privGroup = self.model('group').find({'name': 'GRITSPriv'})[0]
        user = self.model('user').createUser(**privUser)
        self.model('group').addUser(privGroup, user)

        requests(user, (200, 200))

    def testGritsSearch(self):

        def check(user, priv):
            resp = self.request(
                path='/resource/grits',
                method='GET',
                user=user
            )
            self.assertStatusOk(resp)

            self.assertEqual(len(resp.json), len(incidents))

            for i in resp.json:
                found = False
                self.assertTrue(priv or 'private' not in i)
                for incident in incidents:
                    if incident['name'] == i['name']:
                        found = True
                        for key in incident:
                            if key == 'private' and not priv:
                                continue
                            v1 = incident[key]
                            v2 = i[key]
                            if key == 'meta' or key == 'private':
                                self.assertHasKeys(v1, v2.keys())
                                for k in v1:
                                    self.assertEqual(str(v1[k]), str(v2[k]))
                            else:
                                self.assertEqual(str(v1), str(v2))
            self.assertTrue(found)

            resp = self.request(
                path='/resource/grits',
                method='GET',
                user=user,
                params={
                    'geoJSON': 1
                }
            )
            self.assertStatusOk(resp)

            if not priv:
                for i in resp.json['features']:
                    self.assertNotHasKeys(i['properties'], ['privatekey1'])
            else:
                for i in resp.json['features']:
                    self.assertHasKeys(i['properties'], ['privatekey1'])

        self.setUpGroups()
        resp = self.request(
            path='/resource/grits/folderId',
            method='GET',
            user=self.admin
        )
        self.assertStatusOk(resp)
        folder = resp.json

        for incident in incidents:
            resp = self.request(
                path='/item',
                method='POST',
                user=self.admin,
                params={
                    'folderId': folder,
                    'name': incident['name'],
                    'description': incident['description']
                }
            )
            self.assertStatusOk(resp)

#            resp = self.request(
#                path='/item/%s/metadata' % str(resp.json['_id']),
#                method='PUT',
#                user=self.admin,
#                body=bson.json_util.dumps(incident['meta']),
#                type='application/json'
#            )
#            self.assertStatusOk(resp)

            # need to handle lack of bson in item metadata...
            for key in ['_id', 'creatorId', 'folderId']:
                resp.json[key] = ObjectId(resp.json[key])
            self.model('item').setMetadata(resp.json, incident['meta'])

            resp = self.request(
                path='/resource/grits/private/%s' % str(resp.json['_id']),
                method='PUT',
                user=self.admin,
                body=json.dumps(incident['private']),
                type='application/json'
            )
            self.assertStatusOk(resp)

        gritsGroup = self.model('group').find({'name': 'GRITS'})[0]
        g = self.model('user').createUser(**gritsUser)
        self.model('group').addUser(gritsGroup, g)

        privGroup = self.model('group').find({'name': 'GRITSPriv'})[0]
        p = self.model('user').createUser(**privUser)
        self.model('group').addUser(privGroup, p)

        resp = self.request(
            path='/resource/grits',
            method='GET',
            user=self.normalUser
        )
        self.assertStatus(resp, 403)

        check(self.admin, True)
        check(p, True)
        check(g, False)

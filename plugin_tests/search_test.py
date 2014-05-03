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

import bson.json_util

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


def setUpModule():
    base.enabledPlugins.append('gritsSearch')

    base.startServer()


def tearDownModule():
    base.stopServer()


class GritsSearchTestCase(base.TestCase):

    def setUp(self):
        base.TestCase.setUp(self)

        # Create users
        self.admin = self.model('user').createUser(**admin)
        self.gritsUser = self.model('user').createUser(**gritsUser)
        self.normalUser = self.model('user').createUser(**normalUser)

    def testGritsSearch(self):
        """
        Test resource/grits endpoint
        """
        pass

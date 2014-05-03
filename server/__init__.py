
import os
import re
import random
from dateutil.parser import parse as dateParse
from datetime import datetime, timedelta

import json
import bson.json_util
from bson.objectid import ObjectId
from bson.json_util import dumps

from girder import events
from girder.api.rest import Resource, RestException
from girder.api.describe import Description
from girder.utility.model_importer import ModelImporter
from girder.constants import AccessType

config = {
    'collectionName': 'healthmap',
    'folderName': 'allAlerts',
    'user': 'grits',
    'group': 'GRITS',
}


def findOne(model, query):

    item = list(model.find(query=query, limit=1))
    if len(item) == 0:
        item = None
    else:
        item = item[0]
    return item


def getFolderID():

    userModel = ModelImporter().model('user')
    user = findOne(userModel, {'login': config['user']})

    if user is None:
        raise Exception('Could not find existing user: %s' % config['user'])

    groupModel = ModelImporter().model('group')
    group = findOne(groupModel, {'name': config['group']})

    if group is None:
        group = groupModel.createGroup(
            name=config['group'],
            creator=user,
            description='Allows access to the healthmap incident database',
            public=False
        )
        groupModel.addUser(group, user, level=AccessType.ADMIN)

    collectionModel = ModelImporter().model('collection')
    collection = findOne(
        model=collectionModel,
        query={'name': config['collectionName']},
    )

    if collection is None:
        collection = collectionModel.createCollection(
            name=config['collectionName'],
            creator=user,
            description='Healthmap incident database',
            public=False
        )
        collectionModel.setGroupAccess(
            doc=collection,
            group=group,
            level=AccessType.READ
        )

    folderModel = ModelImporter().model('folder')
    folder = findOne(
        model=folderModel,
        query={
            'name': config['folderName'],
            'parentId': collection['_id']
        }
    )

    if folder is None:
        folder = folderModel.createFolder(
            parent=collection,
            name=config['folderName'],
            description='Incident item folder',
            parentType='collection',
            public=False,
            creator=user
        )
        folderModel.setGroupAccess(
            doc=folder,
            group=group,
            level=AccessType.READ
        )
    return folder['_id']


class GRITSDatabase(Resource):
    def __init__(self, folderId):
        self.folderId = folderId
        self._symptomsTable = None

    @classmethod
    def togeoJSON(cls, records):
        output = []
        for record in records:
            meta = record['meta']
            output.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [meta.pop('longitude'), meta.pop('latitude')]
                },
                'properties': {
                    'id': record.get('name'),
                    'summary': record.get('description'),
                    'description': meta.get('description'),
                    'updated': str(record['updated']),
                    'added': str(record['created']),
                    'link': meta.get('link'),
                    'date': str(meta.get('date')),
                    'country': meta.get('country'),
                    'rating': meta.get('rating'),
                    'feed': meta.get('feed'),
                    'disease': meta.get('disease'),
                    'species': meta.get('species'),
                    'symptoms': meta.get('symptoms')
                }
            })
        return {
            'type': 'FeatureCollection',
            'features': output
        }

    @staticmethod
    def selectFromCDF(val, table):
        index = map(lambda x: x >= val, table['cdf']).index(True)
        return table['value'][index]

    def getSymptomFromId(self, id):
        # lazy load symptoms table
        if self._symptomsTable is None:
            f = open(os.path.join(
                os.path.dirname(__file__),
                'symptomsHist.json'
            ), 'r').read()
            self._symptomsTable = json.loads(f)

        random.seed(id)  # set seed for repeatable results
        nSymptoms = self.selectFromCDF(
            random.random(),
            self._symptomsTable['nSymptoms']
        )

        nSymptoms = min(
            nSymptoms,
            len(self._symptomsTable['symptoms']['value'])
        )
        symptoms = []
        for i in xrange(nSymptoms):
            repeat = True
            while repeat:
                s = self.selectFromCDF(
                    random.random(),
                    self._symptomsTable['symptoms']
                )
                try:
                    symptoms.index(s)
                except ValueError:
                    symptoms.append(s)
                    repeat = False
        return symptoms

    def addToQuery(self, query, params, key, useRegex, itemKey=None):
        value = params.get(key)
        if value is not None:
            if itemKey is None:
                itemKey = 'meta.' + key
            if useRegex:
                query[itemKey] = re.compile(value)
            else:
                try:
                    value = bson.json_util.loads(value)
                except ValueError:
                    value = [value]
                query[itemKey] = {'$in': value}
        return self

    def gritsSearch(self, params):

        user = self.getCurrentUser()
        folderModel = ModelImporter().model('folder')
        folder = folderModel.find({'_id': self.folderId})
        if folder.count() != 1:
            raise RestException("Folder ID configured incorrectly")
        folder = folder[0]
        if not folderModel.hasAccess(folder, user=user, level=AccessType.READ):
            raise RestException("Access denied")

        limit, offset, sort = self.getPagingParameters(params, 'meta.date')
        sDate = dateParse(params.get('start', '1990-01-01'))
        eDate = dateParse(params.get('end', str(datetime.now())))
        useRegex = 'disableRegex' not in params

        query = {
            'folderId': self.folderId,
            'meta.date': {'$gte': sDate, '$lt': eDate}
        }

        self.addToQuery(query, params, 'country', useRegex)
        self.addToQuery(query, params, 'disease', useRegex)
        self.addToQuery(query, params, 'species', useRegex)
        self.addToQuery(query, params, 'feed', useRegex)
        self.addToQuery(query, params, 'description', useRegex)
        self.addToQuery(query, params, 'id', useRegex, 'name')

        model = ModelImporter().model('item')
        cursor = model.find(
            query=query,
            fields=None,
            offset=offset,
            limit=limit,
            sort=sort
        )
        result = list(cursor)
        if 'randomSymptoms' in params:
            try:
                filterBySymptom = set(json.loads(params['filterSymptoms']))
            except Exception:
                filterBySymptom = False
            filtered = []
            for r in result:
                r['meta']['symptoms'] = self.getSymptomFromId(r['_id'])
                if filterBySymptom:
                    s2 = set(r['meta']['symptoms'])
                    if not filterBySymptom.isdisjoint(s2):
                        filtered.append(r)
                else:
                    filtered.append(r)
            result = filtered

        if 'geoJSON' in params:
            result = self.togeoJSON(result)
        return result

    gritsSearch.description = (
        Description("Perform a query on the GRITS incident database.")
        .notes(
            "The country, disease, species, feed, and " +
            "description parameters accept regular expressions."
        )
        .param(
            "start",
            "The start date of the query (inclusive)",
            required=False
        )
        .param(
            "end",
            "The end date of the query (exclusive)",
            required=False
        )
        .param(
            "country",
            "The country where the incident occurred",
            required=False
        )
        .param(
            "disease",
            "The name of the disease",
            required=False
        )
        .param(
            "species",
            "The species named in the report",
            required=False
        )
        .param(
            "feed",
            "The feed where the report originated",
            required=False
        )
        .param(
            "description",
            "Match words listed in the incident description field",
            required=False
        )
        .param(
            "id",
            "Match by internal incident identification number",
            required=False
        )
        .param(
            "limit",
            "The number of items to return (default=50)",
            required=False,
            dataType='int'
        )
        .param(
            "offset",
            "Offset into the result set (default=0)",
            required=False,
            dataType='int'
        )
        .param(
            "geoJSON",
            "Return the query as a geoJSON object " +
            "when this parameter is present",
            required=False,
            dataType='bool'
        )
        .errorResponse()
    )


def load(info):
    db = GRITSDatabase(getFolderID())
    info['apiRoot'].resource.route('GET', ('grits',), db.gritsSearch)

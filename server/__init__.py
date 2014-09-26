
import os
import re
import random
from dateutil.parser import parse as dateParse
from datetime import datetime, timedelta

import json
import bson.json_util
from bson.objectid import ObjectId
from bson.json_util import dumps

import cherrypy

from girder import events
from girder.api.rest import Resource, RestException, loadmodel
from girder.api.describe import Description
from girder.utility.model_importer import ModelImporter
from girder.constants import AccessType
from girder.models.model_base import AccessException

config = {
    'collectionName': 'healthmap',
    'folderName': 'allAlerts',
    'user': 'grits',
    'group': 'GRITS',
    'groupPriv': 'GRITSPriv'
}


def findOne(model, query):
    item = list(model.find(query=query, limit=1))
    if len(item) == 0:
        item = None
    else:
        item = item[0]
    return item


def getInfo():
    info = {}
    userModel = ModelImporter().model('user')
    user = findOne(userModel, {'login': config['user']})
    info['user'] = user

    if user is None:
        raise RestException(
            'Could not find existing user "%s"' % config['user'] +
            'needed by grits plugin',
            code=405
        )

    groupModel = ModelImporter().model('group')
    group = findOne(groupModel, {'name': config['group']})

    if group is None:
        group = groupModel.createGroup(
            name=config['group'],
            creator=user,
            description='Allows access to the healthmap incident database',
            public=False
        )
        groupModel.setGroupAccess
    groupModel.addUser(group, user, level=AccessType.ADMIN)
    info['group'] = group

    groupPriv = findOne(groupModel, {'name': config['groupPriv']})

    if groupPriv is None:
        groupPriv = groupModel.createGroup(
            name=config['groupPriv'],
            creator=user,
            description='Allows privilaged access to ' +
            'the healthmap incident database',
            public=False
        )
    groupModel.addUser(groupPriv, user, level=AccessType.ADMIN)
    info['groupPriv'] = groupPriv

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
            level=AccessType.READ,
            save=True
        )
    info['collection'] = collection

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
            level=AccessType.READ,
            save=True
        )
    info['folder'] = folder
    return info


def commonErrors(desc):
    desc.description.errorResponse('Permission denied', 403)
    desc.description.errorResponse('"grits" user does not exist', 405)


class GRITSDatabase(Resource):
    def __init__(self):
        self._symptomsTable = None
        self._gritsFolder = None
        self._info = None

    def gritsInfo(self):
        # if self._info is None:
        #     self._info = getInfo()
        # return self._info
        return getInfo()

    def gritsFolder(self):
        return self.gritsInfo()['folder']

    def checkAccess(self, level=AccessType.READ, priv=False, fail=True):
        g = self.gritsInfo()['group']
        p = self.gritsInfo()['groupPriv']
        user = self.getCurrentUser()
        groupModel = ModelImporter().model('group')

        try:
            groupModel.requireAccess(p, user, level)
        except AccessException:
            p = False

        try:
            groupModel.requireAccess(g, user, level)
        except AccessException:
            g = False

        if priv and not p:
            if not fail:
                return False
            raise RestException("Access denied", code=403)

        if not priv and not (p or g):
            if not fail:
                return False
            raise RestException("Access denied", code=403)

        return True

    def gritsFolderId(self, params):
        self.checkAccess()
        return self.gritsFolder()['_id']
    gritsFolderId.description = (
        Description("Get the folder ID of the grits database")
    )
    commonErrors(gritsFolderId)

    def gritsGroupId(self, params):
        self.checkAccess()
        return self.gritsInfo()['group']['_id']
    gritsGroupId.description = (
        Description(
            'Return the group ID for common access to the grits database'
        )
    )
    commonErrors(gritsGroupId)

    def gritsGroupPrivId(self, params):
        self.checkAccess(priv=True)
        return self.gritsInfo()['groupPriv']['_id']
    gritsGroupPrivId.description = (
        Description(
            'Return the group ID for privilaged access to the grits database'
        )
    )
    commonErrors(gritsGroupPrivId)

    def gritsCollectionId(self, params):
        self.checkAccess()
        return self.gritsInfo()['collection']['_id']
    gritsCollectionId.description = (
        Description(
            'Return the collection ID of the grits database'
        )
    )
    commonErrors(gritsCollectionId)

    @classmethod
    def togeoJSON(cls, records):
        output = []
        for record in records:
            meta = record['meta']
            obj = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [
                        meta.pop('longitude'),
                        meta.pop('latitude')
                    ]
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
            }
            if 'private' in record:
                obj['properties'].update(record['private'])
            output.append(obj)
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

    def addToQuery(self, query, params, key, useRegex, itemKey=None, arrayKey=None):
        value = params.get(key)
        if value is not None:
            if itemKey is None:
                itemKey = 'meta.' + key
            if useRegex:
                if arrayKey is None:
                    query[itemKey] = re.compile(value)
                else:
                    query[itemKey] = {'$elemMatch': {}}
                    query[itemKey]['$elemMatch'][arrayKey] = re.compile(value)
            else:
                try:
                    value = bson.json_util.loads(value)
                except ValueError:
                    value = [value]
                if arrayKey is None:
                    query[itemKey] = {'$in': value}
                else:
                    query[itemKey] = {'$elemMatch': {}}
                    query[itemKey]['$elemMatch'][arrayKey] = {'$in': value}
        return self

    @loadmodel(map={'id': 'item'}, model='item', level=AccessType.WRITE)
    def gritsSetPrivateMetadata(self, item, params):
        self.checkAccess(level=AccessType.WRITE, priv=True)
        itemModel = ModelImporter().model('item')

        try:
            metadata = bson.json_util.loads(cherrypy.request.body.read())
        except ValueError:
            raise RestException('Invalid JSON passed in request body.')

        if 'private' not in item:
            item['private'] = dict()

        for k, v in metadata.iteritems():
            if v is None:
                item['private'].pop(k)
            else:
                item['private'][k] = v

        return itemModel.save(item)
    gritsSetPrivateMetadata.description = (
        Description("Create or update private metadata for an incident")
        .notes('Set metadata fields to null in order to delete them.')
        .param(
            'id',
            'The ID of the item.',
            paramType='path'
        )
        .param(
            'body',
            'A JSON object containing the private metadata to add',
            paramType='body'
        )
        .errorResponse('ID was invalid.')
    )
    commonErrors(gritsSetPrivateMetadata)

    def gritsSearch(self, params):

        user = self.getCurrentUser()
        folderModel = ModelImporter().model('folder')
        folder = self.gritsFolder()

        self.checkAccess()

        limit, offset, sort = self.getPagingParameters(params, 'meta.date')
        sDate = dateParse(params.get('start', '1990-01-01'))
        eDate = dateParse(params.get('end', str(datetime.now())))
        useRegex = 'disableRegex' not in params

        query = {
            'folderId': folder['_id'],
            'meta.date': {'$gte': sDate, '$lt': eDate}
        }

        self.addToQuery(query, params, 'country', useRegex)
        self.addToQuery(query, params, 'disease', useRegex)
        self.addToQuery(query, params, 'species', useRegex)
        self.addToQuery(query, params, 'feed', useRegex)
        self.addToQuery(query, params, 'description', useRegex)
        self.addToQuery(query, params, 'diagnosis', useRegex, 'meta.diagnosis.diseases', 'name')
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
        if not self.checkAccess(priv=True, fail=False):
            result = [model.filter(i) for i in result]

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
            "diagnosis",
            "Match disease names in the differential diagnosis of the report",
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
    commonErrors(gritsSearch)


def load(info):
    db = GRITSDatabase()
    info['apiRoot'].resource.route('GET', ('grits',), db.gritsSearch)
    info['apiRoot'].resource.route(
        'GET',
        ('grits', 'folderId'),
        db.gritsFolderId
    )
    info['apiRoot'].resource.route(
        'GET',
        ('grits', 'groupId'),
        db.gritsGroupId
    )
    info['apiRoot'].resource.route(
        'GET',
        ('grits', 'privilegedId'),
        db.gritsGroupPrivId
    )
    info['apiRoot'].resource.route(
        'GET',
        ('grits', 'collectionId'),
        db.gritsCollectionId
    )
    info['apiRoot'].resource.route(
        'PUT',
        ('grits', 'private', ':id'),
        db.gritsSetPrivateMetadata
    )

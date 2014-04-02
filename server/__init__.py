
import os
import re
import hashlib
from dateutil.parser import parse as dateParse
from datetime import datetime, timedelta

import json
from bson.objectid import ObjectId
from bson.json_util import dumps

from girder import events
from girder.api.rest import Resource, RestException
from girder.api.describe import Description
from girder.utility.model_importer import ModelImporter

def getConfig(fname='eha.json'):
    try:
        s = open(os.path.join(os.path.dirname(__file__), fname), 'r').read()
    except Exception:
        s = '{}'
    return json.loads(s)

class EHADatabase(Resource):
    def __init__(self, folderId=None, apiKeys=[]):
        if folderId is None:
            raise Exception("No folderId given in config")
        self.folderId = ObjectId(folderId)
        self.apiKeys = apiKeys

    @classmethod
    def generateAPIKey(cls):
        return hashlib.md5(os.urandom(256)).hexdigest()
    
    @classmethod
    def togeoJSON(cls, records):
        output = []
        for record in records:
            meta = record['meta']
            output.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [ meta.pop('longitude'), meta.pop('latitude') ]
                },
                'properties': { 
                    'id': record['name'],
                    'summary': record['description'],
                    'description': meta['description'],
                    'updated': str(record['updated']),
                    'added': str(record['created']),
                    'link': meta['link'],
                    'date': str(meta['date']),
                    'country': meta['country'],
                    'rating': meta['rating'],
                    'feed': meta['feed'],
                    'disease': meta['disease']
                }
            })
        return {
            'type': 'FeatureCollection',
            'features': output
        }

    def addToQuery(self, query, params, key):
        value = params.get(key)
        if value is not None:
            query['meta.' + key] = re.compile(value)
        return self

    def ehaSearch(self, params):
        if not params.get('apiKey') in self.apiKeys:
            raise RestException("Invalid API key")
        limit, offset, sort = self.getPagingParameters(params, 'meta.date')
        sDate = dateParse(params.get('start', '1990-01-01'))
        eDate = dateParse(params.get('end', str(datetime.now())))

        query = {
                    'folderId': self.folderId,
                    'meta.date': {'$gte': sDate, '$lt': eDate}
                }
        
        self.addToQuery(query, params, 'country')
        self.addToQuery(query, params, 'disease')
        self.addToQuery(query, params, 'species')
        self.addToQuery(query, params, 'feed')
        self.addToQuery(query, params, 'description')

        model = ModelImporter().model('item')
        result = list(model.find(query=query, fields=None, offset=offset, limit=limit, sort=sort))
        if params.has_key('geoJSON'):
            result = self.togeoJSON(result)
        return result

    ehaSearch.description = (
        Description("Perform a query on the Ecohealth Alliance incident database.")
        .notes("The country, disease, species, feed, and description parameters accept regular expressions.")
        .param("apiKey", "The API key granting access to the plugin")
        .param("start", "The start date of the query (inclusive)", required=False)
        .param("end", "The end date of the query (exclusive)", required=False)
        .param("country", "The country where the incident occurred", required=False)
        .param("disease", "The name of the disease", required=False)
        .param("species", "The species named in the report", required=False)
        .param("feed", "The feed where the report originated", required=False)
        .param("description", "Match words listed in the incident description field", required=False)
        .param("limit", "The number of items to return (default=50)", required=False, dataType='int')
        .param("offset", "Offset into the result set (default=0)", required=False, dataType='int')
        .param("geoJSON", "Return the query as a geoJSON object when this parameter is present", required=False, dataType='bool')
        .errorResponse()
    )

def load(info):
    config = getConfig()
    db = EHADatabase(**config)
    info['apiRoot'].resource.route('GET', ('eha',), db.ehaSearch)

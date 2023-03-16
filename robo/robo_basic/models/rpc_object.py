# -*- coding: utf-8 -*-


class RPCobject(object):
    def __init__(self, models_link, model, db, uid, password):
        self.models = models_link
        self.model = model
        self.db = db
        self.uid = uid
        self.password = password
        self.result = [{}]

    def execute(self, func, args=None):
        if args is None:
            args = {}
        if not self.model:
            return False
        if self.result and isinstance(self.result, tuple([list])) and 'id' in self.result[0]:
            id = self.result[0]['id']
        else:
            id = False
        rec_ids = []
        if id:
            rec_ids.append(id)
        try:
            if id:
                self.result = self.models.execute_kw(self.db, self.uid, self.password, self.model, func, rec_ids, args)
            else:
                self.result = self.models.execute_kw(self.db, self.uid, self.password, self.model, func, [], args)
        except:
            return False
        return True

    def search(self, domain):
        if not self.model:
            return False
        try:
            self.result = self.models.execute_kw(self.db, self.uid, self.password, self.model, 'search_read', [domain],
                                                 {'fields': ['id']})
        except:
            return False
        if self.result:
            return True

    def read(self, ids, fields=False):
        if not self.model:
            return False
        if not fields:
            fields = ['id']
        if type(ids) == int:
            ids = [ids]
        try:
            result = self.models.execute_kw(self.db, self.uid, self.password, self.model, 'read', ids,
                                            {'fields': fields})
            if len(result) == 1 and result[0]:
                self.result.update(result[0])
            else:
                self.result = result
        except:
            return False
        return True

    def write(self, vals):
        if not self.model:
            return False
        if not vals:
            return False
        try:
            self.models.execute_kw(self.db, self.uid, self.password, self.model, 'write', [[self.id], vals])
        except:
            return False
        return True

    def create(self, vals):
        if not self.model:
            return False
        try:
            created_id = self.models.execute_kw(self.db, self.uid, self.password, self.model, 'create', [vals])
            if type(created_id) != list:
                created_id = [created_id]
            new_self = RPCobject(self.models, self.model, self.db, self.uid, self.password)
            new_self.result = self.models.execute_kw(self.db, self.uid, self.password, self.model, 'read', created_id,
                                                     {'fields': ['id']})
            return new_self
        except:
            return False

    def __getattr__(self, attr):
        if self.result and attr in self.result[0]:
            return self.result[0].__getitem__(attr)
        elif self.result and attr not in self.result[0]:
            if self.read(self.id, [attr]):
                return self.result[0].__getitem__(attr)
            else:
                return False
        else:
            return False


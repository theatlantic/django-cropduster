import re
from django.contrib.contenttypes.generic import BaseGenericInlineFormSet

class GenericInlineFormSet(BaseGenericInlineFormSet):
	def _construct_form(self, i, **kwargs):
		"""
		Override the id field of the form with our BetaMaxedFormField
		"""
		obj = None
		try:
			obj = self.queryset[i]
			self.form.instance = obj
			# If cache machine exists, invalidate
			try:
				obj.__class__.objects.invalidate(obj)
			except:
				pass
			try:
				# Invalidate parent instance
				self.instance.__class__.objects.invalidate(self.instance)
			except:
				pass
		except:
			pass
		
		qset_ids = [o.id for o in self.queryset]
		if obj is not None and obj.id not in qset_ids:
			qset_ids.append(obj.id)
			queryset = obj.__class__.objects.filter(pk__in=qset_ids)
			self.queryset = queryset
			self._queryset = queryset
		
		self._pre_construct_form(i, **kwargs)
		form = super(GenericInlineFormSet, self)._construct_form(i, **kwargs)
		form = self._post_construct_form(form, i, **kwargs)
		
		# Load in initial data if we have it from a previously submitted
		# (but apparently invalidated) form
		if self.data is not None and len(self.data) > 0:
			for key in self.data.keys():
				if key.find(self.rel_name) == 0:
					match = re.match(self.rel_name + '-(.+)$', key)
					if match:
						field_name = match.group(1)
						if field_name in form.fields:
							field = form.fields[field_name]
							field.initial = self.data.get(key)
		return form
	
	def _pre_construct_form(self, i, **kwargs):
		pass
	
	def _post_construct_form(self, form, i, **kwargs):
		return form

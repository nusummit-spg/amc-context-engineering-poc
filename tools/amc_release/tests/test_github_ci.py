import unittest
from tools.amc_release import github_ci

SHA='a'*40


class GithubCITests(unittest.TestCase):
    def test_all_green_same_sha(self):
        names=github_ci.REQUIRED
        requests=[]
        runs=[{'name':name,'head_sha':SHA,'id':i+1,'conclusion':'success','created_at':'2026-11-11T12:00:00Z'} for i,name in enumerate(names)]
        def req(url,token):
            requests.append(url)
            if url.endswith('/actions/runs?head_sha='+SHA+'&per_page=100'):
                return {'workflow_runs':runs}
            return {'jobs':[{'conclusion':'success'}]}
        out=github_ci.collect('nu/repo',SHA,request=req)
        self.assertEqual(out['status'],'PASS')
        self.assertEqual(len(out['workflows']),4)
        self.assertTrue(all('page=1' in x or '/runs?' in x for x in requests))
    def test_jobless_fails(self):
        def req(url,token):
            if '/jobs?' in url:return {'jobs':[]}
            return {'workflow_runs':[{'id':1,'name':github_ci.REQUIRED[0],'head_sha':SHA,'conclusion':'success'}]}
        self.assertEqual(github_ci.collect('nu/repo',SHA,request=req)['status'],'BLOCK')
    def test_skipped_job_blocks(self):
        def req(url,token):
            if '/jobs?' in url:return {'jobs':[{'conclusion':'success'},{'conclusion':'skipped'}]}
            return {'workflow_runs':[{'id':1,'name':github_ci.REQUIRED[0],'head_sha':SHA,'conclusion':'success'}]}
        self.assertEqual(github_ci.collect('nu/repo',SHA,request=req)['workflows'][github_ci.REQUIRED[0]]['required_skips'],1)
    def test_foreign_sha_not_selected(self):
        def req(url,token):return {'workflow_runs':[{'id':1,'name':github_ci.REQUIRED[0],'head_sha':'b'*40,'conclusion':'success'}]}
        self.assertEqual(github_ci.collect('nu/repo',SHA,request=req)['status'],'BLOCK')
    def test_invalid_repo_refused(self):
        with self.assertRaises(github_ci.GithubCIError):github_ci.collect('https://other.org/x',SHA,request=lambda x,y:{})
    def test_bad_sha_refused(self):
        with self.assertRaises(ValueError):github_ci.collect('nu/repo','abc',request=lambda x,y:{})


if __name__=='__main__': unittest.main()

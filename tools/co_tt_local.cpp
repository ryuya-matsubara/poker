#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <random>
#include <string>
#include <vector>
using namespace std;
template<class T>T readv(ifstream& f){T x;f.read((char*)&x,sizeof(x));if(!f)throw runtime_error("Truncated blueprint");return x;}
int bucket(int a,int b){int hi=max(a/4,b/4),lo=min(a/4,b/4);return hi==lo?hi:(a%4==b%4?13:91)+hi*(hi-1)/2+lo;}
int straight(int mask){for(int r=12;r>=4;r--)if((mask&(31<<(r-4)))==(31<<(r-4)))return r;return (mask&4111)==4111?3:-1;}
uint64_t pack(int cat,vector<int> r){uint64_t v=cat;for(int i=0;i<5;i++)v=v*16+(i<(int)r.size()?r[i]+2:0);return v;}
uint64_t eval(const vector<int>& cards){
 int count[13]={},sm[4]={},sc[4]={},mask=0;
 for(int c:cards){count[c/4]++;mask|=1<<(c/4);sm[c%4]|=1<<(c/4);sc[c%4]++;}
 int fs=-1;for(int s=0;s<4;s++)if(sc[s]>=5){fs=s;int r=straight(sm[s]);if(r>=0)return pack(8,{r});}
 vector<int> q,t,p,single;for(int r=12;r>=0;r--){if(count[r]==4)q.push_back(r);if(count[r]>=3)t.push_back(r);if(count[r]>=2)p.push_back(r);if(count[r])single.push_back(r);}
 if(!q.empty()){int k=single[0]==q[0]?single[1]:single[0];return pack(7,{q[0],k});}
 if(!t.empty()){for(int r:p)if(r!=t[0])return pack(6,{t[0],r});}
 if(fs>=0){vector<int> r;for(int x=12;x>=0;x--)if(sm[fs]&(1<<x))r.push_back(x);r.resize(5);return pack(5,r);}
 int st=straight(mask);if(st>=0)return pack(4,{st});
 if(!t.empty()){vector<int> r={t[0]};for(int x:single)if(x!=t[0]&&r.size()<3)r.push_back(x);return pack(3,r);}
 if(p.size()>=2){vector<int> r={p[0],p[1]};for(int x:single)if(x!=p[0]&&x!=p[1]){r.push_back(x);break;}return pack(2,r);}
 if(p.size()==1){vector<int> r={p[0]};for(int x:single)if(x!=p[0]&&r.size()<4)r.push_back(x);return pack(1,r);}
 single.resize(5);return pack(0,single);
}
struct Policy{
 map<string,array<vector<float>,169>> h;
 Policy(string path){
  ifstream f(path,ios::binary);int d=readv<uint8_t>(f);vector<vector<int>> sizes;
  for(int i=0;i<d;i++){int n=readv<uint8_t>(f);vector<int> z;for(int j=0;j<n;j++)z.push_back(readv<int32_t>(f));sizes.push_back(z);}
  int limp=readv<uint8_t>(f),sb=readv<int32_t>(f),minjam=readv<uint8_t>(f);auto it=readv<uint64_t>(f),n=readv<uint64_t>(f);
  if(sizes!=vector<vector<int>>{{4,5},{14},{28}}||!limp||sb!=6||minjam!=0)throw runtime_error("Unexpected game configuration");
  for(uint64_t i=0;i<n;i++){
   int b=readv<uint8_t>(f),len=readv<uint16_t>(f);string key(len,' ');f.read(key.data(),len);int a=readv<uint16_t>(f);f.seekg(4*a,ios::cur);vector<float> v(a);f.read((char*)v.data(),4*a);
   if(key.empty()||key==string(1,'\0')||(key.size()>=2&&key[0]==0&&key[1]==2)){
    double sum=0;for(float x:v){if(!isfinite(x)||x<0)throw runtime_error("Invalid strategy");sum+=x;}
    if(sum>0)for(float &x:v)x/=sum;else for(float &x:v)x=1.0/a;h[key][b]=v;
   }
  }if(!f)throw runtime_error("Truncated blueprint");cerr<<"Loaded "<<it<<" iterations, "<<h.size()<<" relevant histories\n";
 }
 const vector<float>& get(const string& k,int b){auto i=h.find(k);if(i==h.end()||i->second[b].empty())throw runtime_error("Missing frozen policy; refusing invented fallback");return i->second[b];}
};
int main(int argc,char**argv){
 if(argc<4)return 1;Policy policy(argv[1]);int n=stoi(argv[2]);mt19937_64 rng(stoull(argv[3]));uniform_real_distribution<double> u(0,1);
 // Independent five-card subset check of the direct seven-card evaluator.
 for(int z=0;z<10000;z++){vector<int>d(52);for(int i=0;i<52;i++)d[i]=i;shuffle(d.begin(),d.end(),rng);vector<int>c(d.begin(),d.begin()+7);uint64_t best=0;for(int a=0;a<7;a++)for(int b=a+1;b<7;b++){vector<int>x;for(int j=0;j<7;j++)if(j!=a&&j!=b)x.push_back(c[j]);best=max(best,eval(x));}assert(best==eval(c));}
 assert(bucket(32,33)==8);assert(eval({48,44,40,36,32,1,6})>eval({48,49,50,51,44,40,36}));
 double sum=0,sq=0;long long attempts=0,allfold=0,multi=0;array<long long,169>mp{};array<long long,6>calls{};
 const auto &tt=policy.get(string("\0\2",2),8);cerr<<"CO TT probabilities:";for(float x:tt)cerr<<" "<<x;cerr<<"\n";
 for(int acc=0;acc<n;){attempts++;vector<int>d;for(int c=0;c<52;c++)if(c!=32&&c!=33)d.push_back(c);
  int holes[6][2];holes[2][0]=32;holes[2][1]=33;int k=0;for(int j=0;j<15;j++){int x=j+rng()%(50-j);swap(d[j],d[x]);}
  for(int p: {0,1,3,4,5})for(int j=0;j<2;j++)holes[p][j]=d[k++];
  if(u(rng)>policy.get("",bucket(holes[0][0],holes[0][1]))[0])continue;
  if(u(rng)>policy.get(string(1,'\0'),bucket(holes[1][0],holes[1][1]))[2])continue;
  acc++;mp[bucket(holes[1][0],holes[1][1])]++;
  bool active[6]={false,false,true,false,false,false};double bets[6]={0,2.5,20,0,.5,1};string history("\0\2\3",3);int num=1;
  for(int p:{3,4,5,1}){const auto &v=policy.get(history,bucket(holes[p][0],holes[p][1]));if(v.size()!=2)throw runtime_error("Jam-facing actions must be fold/call-all-in");int action=u(rng)<v[0]?0:1;history.push_back(action);if(action){active[p]=true;bets[p]=20;num++;calls[p]++;}}
  double pot=0;for(double b:bets)pot+=b;double payoff[6];for(int p=0;p<6;p++)payoff[p]=-bets[p];
  vector<int>winners;if(num==1){allfold++;winners={2};}else{if(num>2)multi++;uint64_t best=0;for(int p=0;p<6;p++)if(active[p]){vector<int>c={holes[p][0],holes[p][1],d[10],d[11],d[12],d[13],d[14]};auto e=eval(c);if(e>best){best=e;winners={p};}else if(e==best)winners.push_back(p);}}
  for(int p:winners)payoff[p]+=pot/winners.size();double total=0;for(double x:payoff)total+=x;assert(abs(total)<1e-9);
  sum+=payoff[2];sq+=payoff[2]*payoff[2];
 }
 double mean=sum/n,se=sqrt(max(0.0,(sq-sum*sum/n)/(n-1)/n));cout<<setprecision(12)<<"{\"samples\":"<<n<<",\"attempts\":"<<attempts<<",\"jam_ev_bb\":"<<mean<<",\"se_bb\":"<<se<<",\"ci95_bb\":["<<mean-1.96*se<<","<<mean+1.96*se<<"],\"all_fold_rate\":"<<double(allfold)/n<<",\"multiway_rate\":"<<double(multi)/n<<",\"call_rates_by_seat\":[";for(int p=0;p<6;p++){if(p)cout<<",";cout<<double(calls[p])/n;}cout<<"],\"conditional_mp_bucket_counts\":[";for(int b=0;b<169;b++){if(b)cout<<",";cout<<mp[b];}cout<<"]}\n";
}

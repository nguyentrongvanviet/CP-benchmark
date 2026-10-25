#include <bits/stdc++.h>
using namespace std;
int main(){ios::sync_with_stdio(false);cin.tie(nullptr);int n;cin>>n;vector<int>a(n);for(int i=0;i<n;i++){cin>>a[i];if(i)a[i]+=a[i-1];}int m;cin>>m;while(m--){int q;cin>>q;cout<<upper_bound(a.begin(),a.end(),q)-a.begin()+1<<"\n";}return 0;}
